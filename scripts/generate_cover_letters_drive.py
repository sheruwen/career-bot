#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import requests
from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from pypdf import PdfReader


def _sanitize_folder_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] if cleaned else "untitled_job"


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _detect_lang(job: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(job.get("title", "")),
            str(job.get("company", "")),
            " ".join(job.get("reasons", []) if isinstance(job.get("reasons"), list) else []),
        ]
    )
    return "cn" if _contains_cjk(text) else "en"


def _extract_resume_text(pdf_path: Path, limit_chars: int = 6000) -> str:
    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    text = re.sub(r"\s+", " ", " ".join(chunks)).strip()
    return text[:limit_chars]


class DriveClient:
    def __init__(
        self,
        auth_mode: str,
        credentials_file: str = "",
        oauth_client_file: str = "",
        oauth_token_file: str = "token_drive.json",
    ):
        scopes = ["https://www.googleapis.com/auth/drive"]
        if auth_mode == "oauth":
            self.creds = self._load_oauth_credentials(
                oauth_client_file=oauth_client_file,
                oauth_token_file=oauth_token_file,
                scopes=scopes,
            )
        else:
            self.creds = service_account.Credentials.from_service_account_file(
                credentials_file, scopes=scopes
            )
        self.creds.refresh(Request())
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.creds.token}"})

    def _load_oauth_credentials(
        self, oauth_client_file: str, oauth_token_file: str, scopes: list[str]
    ) -> user_credentials.Credentials:
        token_path = Path(oauth_token_file)
        creds: user_credentials.Credentials | None = None
        if token_path.exists():
            creds = user_credentials.Credentials.from_authorized_user_file(
                str(token_path), scopes
            )
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds

        flow = InstalledAppFlow.from_client_secrets_file(oauth_client_file, scopes=scopes)
        creds = flow.run_local_server(port=0, open_browser=False)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def export_google_doc_text(self, file_id: str) -> str:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
        params = {"mimeType": "text/plain"}
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.text

    def download_file(self, file_id: str, out_path: Path) -> None:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {"alt": "media"}
        resp = self.session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)

    def get_file_meta(self, file_id: str) -> dict[str, Any]:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {"fields": "id,name,mimeType", "supportsAllDrives": "true"}
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def ensure_subfolder(self, parent_id: str, folder_name: str) -> str:
        query = (
            f"'{parent_id}' in parents and trashed=false "
            f"and mimeType='application/vnd.google-apps.folder' and name='{folder_name}'"
        )
        url = "https://www.googleapis.com/drive/v3/files"
        params = {
            "q": query,
            "fields": "files(id,name)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        files = resp.json().get("files", [])
        if files:
            return files[0]["id"]

        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        create = self.session.post(
            url,
            params={"supportsAllDrives": "true"},
            json=metadata,
            timeout=30,
        )
        create.raise_for_status()
        return create.json()["id"]

    def upload_text_file(self, parent_id: str, name: str, text: str) -> str:
        boundary = "-------314159265358979323846"
        metadata = {"name": name, "parents": [parent_id]}
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata, ensure_ascii=False)}\r\n"
            f"--{boundary}\r\n"
            "Content-Type: text/plain; charset=UTF-8\r\n\r\n"
            f"{text}\r\n"
            f"--{boundary}--"
        )
        url = "https://www.googleapis.com/upload/drive/v3/files"
        headers = {"Content-Type": f"multipart/related; boundary={boundary}"}
        resp = self.session.post(
            url,
            params={"uploadType": "multipart", "supportsAllDrives": "true"},
            headers=headers,
            data=body.encode("utf-8"),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def list_child_folders(self, parent_id: str) -> list[dict[str, str]]:
        query = (
            f"'{parent_id}' in parents and trashed=false "
            "and mimeType='application/vnd.google-apps.folder'"
        )
        url = "https://www.googleapis.com/drive/v3/files"
        params = {
            "q": query,
            "fields": "files(id,name)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        files = resp.json().get("files", [])
        return [{"id": f["id"], "name": f["name"]} for f in files]

    def folder_has_file(self, folder_id: str, name: str) -> bool:
        query = f"'{folder_id}' in parents and trashed=false and name='{name}'"
        url = "https://www.googleapis.com/drive/v3/files"
        params = {
            "q": query,
            "fields": "files(id,name)",
            "pageSize": 1,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return bool(resp.json().get("files", []))

    def delete_file(self, file_id: str) -> None:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        resp = self.session.delete(
            url, params={"supportsAllDrives": "true"}, timeout=30
        )
        resp.raise_for_status()


def _load_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj.get("matched_jobs", []) if isinstance(obj, dict) else []


def _select_latest_output(output_dir: Path, prefix: str) -> Path | None:
    candidates = sorted(output_dir.glob(f"{prefix}_*.json"))
    return candidates[-1] if candidates else None


def _build_cover_letter(
    template_text: str,
    job: dict[str, Any],
    resume_summary: str,
    source: str,
) -> str:
    reasons = job.get("reasons", [])
    reasons_text = "; ".join(reasons) if isinstance(reasons, list) else str(reasons)
    mapping = {
        "{{company}}": str(job.get("company", "")),
        "{{job_title}}": str(job.get("title", "")),
        "{{job_url}}": str(job.get("url", "")),
        "{{job_source}}": source,
        "{{job_city}}": str(job.get("city", "")),
        "{{job_reasons}}": reasons_text,
        "{{date}}": dt.date.today().isoformat(),
        "{{resume_summary}}": resume_summary,
    }
    rendered = template_text
    replaced = False
    for k, v in mapping.items():
        if k in rendered:
            rendered = rendered.replace(k, v)
            replaced = True

    if replaced:
        return rendered.strip() + "\n"

    intro = (
        f"應徵職位：{job.get('title', '')}\n"
        f"公司：{job.get('company', '')}\n"
        f"來源：{source}\n"
        f"職缺連結：{job.get('url', '')}\n\n"
    )
    focus = f"職缺匹配重點：{reasons_text}\n\n" if reasons_text else ""
    resume_block = f"履歷摘要：{resume_summary}\n\n" if resume_summary else ""
    return (intro + focus + resume_block + template_text).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate per-job cover letters to Google Drive")
    parser.add_argument("--drive-folder-id", required=True, help="Parent Drive folder ID")
    parser.add_argument("--template-cn-id", required=True, help="Google Doc file ID")
    parser.add_argument("--template-en-id", required=True, help="Google Doc file ID")
    parser.add_argument("--resume-file-id", required=True, help="Resume file ID (pdf/md/txt/google doc)")
    parser.add_argument(
        "--auth-mode",
        choices=["service_account", "oauth"],
        default="service_account",
    )
    parser.add_argument("--credentials-file", default="", help="service account json path")
    parser.add_argument("--oauth-client-file", default="", help="OAuth desktop client json path")
    parser.add_argument("--oauth-token-file", default="token_drive.json")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--date", default="", help="YYYY-MM-DD, default latest output files")
    parser.add_argument("--limit", type=int, default=0, help="只處理前 N 筆，0 表示全部")
    parser.add_argument(
        "--clear-others",
        action="store_true",
        help="清除同父資料夾下其餘由本腳本產生的職缺資料夾（保留本次處理者）",
    )
    args = parser.parse_args()
    if args.auth_mode == "service_account" and not args.credentials_file:
        raise RuntimeError("--auth-mode service_account 時必須提供 --credentials-file")
    if args.auth_mode == "oauth" and not args.oauth_client_file:
        raise RuntimeError("--auth-mode oauth 時必須提供 --oauth-client-file")

    output_dir = Path(args.output_dir)
    if args.date:
        p104 = output_dir / f"jobs_104_{args.date}.json"
        pcake = output_dir / f"jobs_cake_{args.date}.json"
    else:
        p104 = _select_latest_output(output_dir, "jobs_104")
        pcake = _select_latest_output(output_dir, "jobs_cake")

    if not p104 and not pcake:
        raise RuntimeError("找不到 jobs_104 / jobs_cake 輸出檔")

    drive = DriveClient(
        auth_mode=args.auth_mode,
        credentials_file=args.credentials_file,
        oauth_client_file=args.oauth_client_file,
        oauth_token_file=args.oauth_token_file,
    )
    template_cn = drive.export_google_doc_text(args.template_cn_id)
    template_en = drive.export_google_doc_text(args.template_en_id)

    resume_meta = drive.get_file_meta(args.resume_file_id)
    resume_mime = resume_meta.get("mimeType", "")
    if resume_mime == "application/vnd.google-apps.document":
        resume_summary = drive.export_google_doc_text(args.resume_file_id)
    elif resume_mime in ("text/plain", "text/markdown"):
        tmp_resume_txt = Path("/tmp/resume_input.txt")
        drive.download_file(args.resume_file_id, tmp_resume_txt)
        resume_summary = tmp_resume_txt.read_text(encoding="utf-8", errors="ignore")
    elif resume_mime == "application/pdf":
        tmp_resume_pdf = Path("/tmp/resume_input.pdf")
        drive.download_file(args.resume_file_id, tmp_resume_pdf)
        resume_summary = _extract_resume_text(tmp_resume_pdf, limit_chars=6000)
    else:
        # Fallback: try plain-text decode for unknown but text-like files.
        tmp_resume_raw = Path("/tmp/resume_input.raw")
        drive.download_file(args.resume_file_id, tmp_resume_raw)
        resume_summary = tmp_resume_raw.read_text(encoding="utf-8", errors="ignore")
    resume_summary = re.sub(r"\s+", " ", resume_summary).strip()[:3500]

    jobs: list[tuple[str, dict[str, Any]]] = []
    if p104:
        jobs.extend([("104", j) for j in _load_jobs(p104)])
    if pcake:
        jobs.extend([("cake", j) for j in _load_jobs(pcake)])

    if not jobs:
        print("沒有 matched_jobs，略過 cover letter 生成")
        return 0
    if args.limit > 0:
        jobs = jobs[: args.limit]

    keep_folder_names: set[str] = set()
    for source, job in jobs:
        lang = _detect_lang(job)
        template = template_cn if lang == "cn" else template_en
        company = str(job.get("company", "") or "UnknownCompany")
        title = str(job.get("title", "") or "UnknownRole")
        folder_name = _sanitize_folder_name(f"{company}_{title}")
        keep_folder_names.add(folder_name)
        subfolder_id = drive.ensure_subfolder(args.drive_folder_id, folder_name)
        text = _build_cover_letter(template, job, resume_summary, source)
        drive.upload_text_file(subfolder_id, "cover_letter.txt", text)
        drive.upload_text_file(
            subfolder_id,
            "job_info.json",
            json.dumps({"source": source, "job": job}, ensure_ascii=False, indent=2),
        )
        print(f"created: {folder_name}")

    if args.clear_others:
        for folder in drive.list_child_folders(args.drive_folder_id):
            fid = folder["id"]
            name = folder["name"]
            if name in keep_folder_names:
                continue
            # Only clean folders generated by this script.
            if drive.folder_has_file(fid, "job_info.json"):
                drive.delete_file(fid)
                print(f"deleted: {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
