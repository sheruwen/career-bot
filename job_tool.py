#!/usr/bin/env python3
import argparse
import datetime as dt
import difflib
import email
import imaplib
import json
import os
import re
from dataclasses import dataclass
from email.header import decode_header
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests


@dataclass
class MatchRule:
    include_keywords: list[str]
    require_include_keyword_match: bool
    required_keywords_all: list[str]
    required_keyword_groups: list[list[str]]
    min_required_group_matches: int
    fuzzy_match_enabled: bool
    fuzzy_match_threshold: float
    exclude_keywords: list[str]
    preferred_cities: list[str]
    allowed_cities: list[str]
    include_companies: list[str]
    exclude_companies: list[str]
    include_industry_keywords: list[str]
    require_industry_match: bool
    minimum_salary: int
    require_remote: bool
    minimum_score: int
    top_n: int


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_a = False
        self.current_href = ""
        self.current_text_chunks: list[str] = []
        self.anchors: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for k, v in attrs:
            if k.lower() == "href" and v:
                href = v
                break
        self.in_a = True
        self.current_href = href
        self.current_text_chunks = []

    def handle_data(self, data: str) -> None:
        if self.in_a:
            self.current_text_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self.in_a:
            return
        text = "".join(self.current_text_chunks).strip()
        if self.current_href:
            self.anchors.append({"url": self.current_href.strip(), "text": text})
        self.in_a = False
        self.current_href = ""
        self.current_text_chunks = []


def load_rules(path: Path) -> MatchRule:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    required_groups = raw.get("required_keyword_groups", [])
    if not required_groups and raw.get("required_keywords_all"):
        required_groups = [[kw] for kw in raw.get("required_keywords_all", [])]
    return MatchRule(
        include_keywords=raw.get("include_keywords", []),
        require_include_keyword_match=bool(
            raw.get("require_include_keyword_match", False)
        ),
        required_keywords_all=raw.get("required_keywords_all", []),
        required_keyword_groups=required_groups,
        min_required_group_matches=int(raw.get("min_required_group_matches", 0)),
        fuzzy_match_enabled=bool(raw.get("fuzzy_match_enabled", True)),
        fuzzy_match_threshold=float(raw.get("fuzzy_match_threshold", 0.82)),
        exclude_keywords=raw.get("exclude_keywords", []),
        preferred_cities=raw.get("preferred_cities", []),
        allowed_cities=raw.get("allowed_cities", []),
        include_companies=raw.get("include_companies", []),
        exclude_companies=raw.get("exclude_companies", []),
        include_industry_keywords=raw.get("include_industry_keywords", []),
        require_industry_match=bool(raw.get("require_industry_match", False)),
        minimum_salary=int(raw.get("minimum_salary", 0)),
        require_remote=bool(raw.get("require_remote", False)),
        minimum_score=int(raw.get("minimum_score", 0)),
        top_n=int(raw.get("top_n", 20)),
    )


def _normalize_text_for_match(text: str) -> str:
    lowered = text.lower()
    # Keep CJK and alnum, drop most separators to make "road map" ~= "roadmap".
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", lowered)


def keyword_in_text(text: str, keyword: str, fuzzy: bool, threshold: float) -> bool:
    if not keyword:
        return False
    text_l = text.lower()
    kw_l = keyword.lower()

    if kw_l in text_l:
        return True

    text_n = _normalize_text_for_match(text)
    kw_n = _normalize_text_for_match(keyword)
    if kw_n and kw_n in text_n:
        return True
    if not fuzzy or not kw_n:
        return False

    # Token-level fuzzy matching for English-like terms.
    text_tokens = re.findall(r"[a-z0-9+#._/-]+", text_l)
    for token in text_tokens:
        token_n = _normalize_text_for_match(token)
        if not token_n:
            continue
        if difflib.SequenceMatcher(None, token_n, kw_n).ratio() >= threshold:
            return True

    # N-gram fuzzy matching for multi-word keywords.
    kw_words = re.findall(r"[a-z0-9]+", kw_l)
    words = re.findall(r"[a-z0-9]+", text_l)
    if len(kw_words) >= 2 and len(words) >= len(kw_words):
        k = len(kw_words)
        target = "".join(kw_words)
        for i in range(0, len(words) - k + 1):
            gram = "".join(words[i : i + k])
            if difflib.SequenceMatcher(None, gram, target).ratio() >= threshold:
                return True

    return False


def normalize_job(job: dict[str, Any]) -> dict[str, Any]:
    title = job.get("jobName") or job.get("title") or ""
    company = job.get("custName") or job.get("companyName") or ""
    city = job.get("jobAddrNoDesc") or job.get("city") or ""
    salary = (
        job.get("salaryLow")
        or job.get("salaryMin")
        or job.get("salary")
        or job.get("monthlySalary")
        or 0
    )
    try:
        salary = int(float(salary))
    except (TypeError, ValueError):
        salary = 0
    raw_link = (
        job.get("jobUrl")
        or job.get("link")
        or job.get("jobLink")
        or job.get("url")
        or ""
    )
    if isinstance(raw_link, dict):
        url = (
            raw_link.get("job")
            or raw_link.get("url")
            or raw_link.get("link")
            or ""
        )
    else:
        url = raw_link
    desc = job.get("description") or job.get("jobDescription") or ""
    industry = job.get("coIndustryDesc") or job.get("industry") or ""
    tags = job.get("tags") or job.get("keyword") or []
    if isinstance(tags, str):
        tags = [tags]
    remote = bool(job.get("remote", False))
    return {
        "title": str(title),
        "company": str(company),
        "city": str(city),
        "salary": salary,
        "url": str(url),
        "description": str(desc),
        "industry": str(industry),
        "tags": [str(t) for t in tags],
        "remote": remote,
        "source_raw": job,
    }


def decode_mime_words(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded: list[str] = []
    for text, enc in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded).strip()


def extract_email_bodies(msg: email.message.Message) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(decoded)
            elif content_type == "text/html":
                html_parts.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(decoded)
            else:
                plain_parts.append(decoded)
    return "\n".join(plain_parts), "\n".join(html_parts)


def extract_jobs_from_email(
    subject: str, plain_text: str, html_text: str
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    parser = AnchorParser()
    if html_text:
        parser.feed(html_text)
    for anchor in parser.anchors:
        url = anchor["url"]
        if not url.startswith("http"):
            continue
        if "104.com.tw/job" not in url and "104.com.tw/jobs" not in url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = anchor["text"] or subject
        jobs.append(
            {
                "title": title,
                "company": "",
                "city": "",
                "salary": 0,
                "url": url,
                "description": subject,
                "tags": [],
                "remote": False,
                "source_raw": {"source": "imap_html_anchor"},
            }
        )

    url_pattern = r"https?://[^\s<>\"]+"
    for url in re.findall(url_pattern, plain_text):
        cleaned = url.strip(").,")
        if "104.com.tw/job" not in cleaned and "104.com.tw/jobs" not in cleaned:
            continue
        if cleaned in seen_urls:
            continue
        seen_urls.add(cleaned)
        jobs.append(
            {
                "title": subject,
                "company": "",
                "city": "",
                "salary": 0,
                "url": cleaned,
                "description": plain_text[:300],
                "tags": [],
                "remote": False,
                "source_raw": {"source": "imap_plain_url"},
            }
        )
    return jobs


def score_job(job: dict[str, Any], rules: MatchRule) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    company_lower = job["company"].lower()
    fulltext = " ".join(
        [
            job["title"].lower(),
            job["company"].lower(),
            job["city"].lower(),
            job.get("industry", "").lower(),
            job["description"].lower(),
            " ".join(t.lower() for t in job["tags"]),
        ]
    )

    for kw in rules.exclude_keywords:
        if keyword_in_text(
            fulltext, kw, rules.fuzzy_match_enabled, rules.fuzzy_match_threshold
        ):
            return -9999, [f"排除關鍵字: {kw}"]

    required_groups = rules.required_keyword_groups
    if not required_groups:
        required_groups = [[kw] for kw in rules.required_keywords_all]
    if required_groups:
        group_hits = 0
        missing_groups: list[str] = []
        for group in required_groups:
            if not group:
                continue
            if any(
                keyword_in_text(
                    fulltext,
                    term,
                    rules.fuzzy_match_enabled,
                    rules.fuzzy_match_threshold,
                )
                for term in group
            ):
                group_hits += 1
            else:
                missing_groups.append(" / ".join(group))
        required_hits = rules.min_required_group_matches or len(required_groups)
        if group_hits < required_hits:
            return -9999, [f"必要群組命中不足: {group_hits}/{required_hits}"]

    if rules.allowed_cities and job["city"]:
        city = job["city"].strip()
        city_allowed = any(
            allowed.strip() and allowed.strip() in city for allowed in rules.allowed_cities
        )
        if not city_allowed:
            return -9999, [f"不在允許城市: {job['city']}"]

    for c in rules.exclude_companies:
        if c.lower() in company_lower:
            return -9999, [f"排除公司: {c}"]

    if rules.include_industry_keywords:
        industry_text = job.get("industry", "").lower()
        industry_hit = any(kw.lower() in industry_text for kw in rules.include_industry_keywords)
        industry_loose_hit = any(
            kw.lower() in industry_text or kw.lower() in fulltext
            for kw in rules.include_industry_keywords
        )
        if rules.require_industry_match and not industry_hit:
            return -9999, ["非目標產業（軟體優先）"]
        if industry_loose_hit:
            score += 8
            reasons.append(f"產業符合: {job.get('industry', '') or '軟體相關關鍵字'}")

    include_hit = 0
    for kw in rules.include_keywords:
        if keyword_in_text(
            fulltext, kw, rules.fuzzy_match_enabled, rules.fuzzy_match_threshold
        ):
            include_hit += 1
            score += 10
            reasons.append(f"關鍵字符合: {kw}")

    if rules.require_include_keyword_match and include_hit == 0:
        return -9999, ["未命中任何 include_keywords"]

    for c in rules.include_companies:
        if c.lower() in company_lower:
            score += 8
            reasons.append(f"偏好公司: {c}")

    if rules.preferred_cities and job["city"]:
        city = job["city"].strip()
        city_preferred = any(
            preferred.strip() and preferred.strip() in city
            for preferred in rules.preferred_cities
        )
        if city_preferred:
            score += 6
            reasons.append(f"地點符合: {job['city']}")

    if job["salary"] <= 0:
        reasons.append("薪資未知")
    elif job["salary"] >= rules.minimum_salary:
        score += 6
        reasons.append(f"薪資符合: >= {rules.minimum_salary}")
    else:
        score -= 4
        reasons.append(f"薪資偏低: {job['salary']}")

    if rules.require_remote:
        if job["remote"]:
            score += 5
            reasons.append("支援遠端")
        else:
            score -= 8
            reasons.append("不支援遠端")

    return score, reasons


def fetch_jobs() -> list[dict[str, Any]]:
    api_url = os.getenv("JOB_API_URL", "").strip()
    token = os.getenv("JOB_API_TOKEN", "").strip()
    query = os.getenv("JOB_API_QUERY", "").strip()
    timeout = int(os.getenv("JOB_API_TIMEOUT", "20"))

    if not api_url:
        raise RuntimeError("請先設定 JOB_API_URL")

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params: dict[str, str] = {}
    if query:
        params["keyword"] = query

    resp = requests.get(api_url, headers=headers, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    # 常見格式: {"data": {"list": [...]}} 或 {"data": [...]} 或 {"jobs": [...]}
    jobs = []
    if isinstance(data, dict):
        if isinstance(data.get("jobs"), list):
            jobs = data["jobs"]
        elif isinstance(data.get("data"), list):
            jobs = data["data"]
        elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("list"), list):
            jobs = data["data"]["list"]
    elif isinstance(data, list):
        jobs = data

    if not isinstance(jobs, list):
        raise RuntimeError("API 回傳格式不符合預期，找不到職缺列表")
    return jobs


def fetch_jobs_from_104_web() -> list[dict[str, Any]]:
    keyword = os.getenv("WEB104_KEYWORD", "產品經理").strip()
    area = os.getenv("WEB104_AREA", "6001001000").strip()
    pages = int(os.getenv("WEB104_PAGES", "1"))
    order = os.getenv("WEB104_ORDER", "15").strip()
    asc = os.getenv("WEB104_ASC", "0").strip()
    timeout = int(os.getenv("WEB104_TIMEOUT", "20"))
    url = os.getenv("WEB104_API_URL", "https://www.104.com.tw/jobs/search/api/jobs").strip()

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.104.com.tw/jobs/search/",
        "Accept": "application/json, text/plain, */*",
    }
    jobs: list[dict[str, Any]] = []
    for page in range(1, max(1, pages) + 1):
        params = {
            "keyword": keyword,
            "area": area,
            "page": str(page),
            "order": order,
            "asc": asc,
            "mode": "s",
            "jobsource": "2018indexpoc",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not isinstance(data, list) or not data:
            break
        jobs.extend(data)
    return jobs


def fetch_jobs_from_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"找不到測試資料檔: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
        return [normalize_job(x) for x in raw["jobs"]]
    if isinstance(raw, list):
        return [normalize_job(x) for x in raw]
    raise RuntimeError("測試資料格式錯誤，請使用 list 或 {'jobs': [...]} 格式")


def fetch_jobs_from_imap() -> list[dict[str, Any]]:
    host = os.getenv("IMAP_HOST", "").strip()
    port = int(os.getenv("IMAP_PORT", "993"))
    user = os.getenv("IMAP_USER", "").strip()
    password = os.getenv("IMAP_PASSWORD", "").strip()
    mailbox = os.getenv("IMAP_MAILBOX", "INBOX").strip()
    since_days = int(os.getenv("IMAP_SINCE_DAYS", "1"))
    from_filter = os.getenv("IMAP_FROM_FILTER", "104").strip()
    subject_filter = os.getenv("IMAP_SUBJECT_FILTER", "").strip()

    if not host or not user or not password:
        raise RuntimeError("請先設定 IMAP_HOST, IMAP_USER, IMAP_PASSWORD")

    since_date = (dt.datetime.now() - dt.timedelta(days=since_days)).strftime("%d-%b-%Y")
    client = imaplib.IMAP4_SSL(host, port)
    client.login(user, password)
    client.select(mailbox)

    criteria = [f'(SINCE "{since_date}")']
    status, ids_data = client.search(None, *criteria)
    if status != "OK":
        client.logout()
        raise RuntimeError("IMAP 查詢失敗")

    ids = ids_data[0].split()
    jobs: list[dict[str, Any]] = []
    for msg_id in ids:
        status, msg_data = client.fetch(msg_id, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            continue
        msg = email.message_from_bytes(raw)
        from_text = decode_mime_words(msg.get("From"))
        subject = decode_mime_words(msg.get("Subject"))
        if from_filter and from_filter.lower() not in from_text.lower():
            continue
        if subject_filter and subject_filter.lower() not in subject.lower():
            continue
        plain_text, html_text = extract_email_bodies(msg)
        jobs.extend(extract_jobs_from_email(subject, plain_text, html_text))
    client.logout()
    return jobs


def render_markdown(matched: list[dict[str, Any]], date_str: str) -> str:
    lines = [
        f"# 每日職缺清單 ({date_str})",
        "",
        "來源: https://www.104.com.tw/jobs/search/",
        "使用限制: 僅供個人求職整理，不對外提供 API 或下載。",
        "",
    ]
    if not matched:
        lines.append("今天沒有符合條件的職缺。")
        return "\n".join(lines)

    for i, m in enumerate(matched, 1):
        lines.append(f"## {i}. {m['title']} - {m['company']}")
        lines.append(f"- 地點: {m['city'] or '未提供'}")
        salary_text = "面議" if int(m.get("salary", 0)) <= 0 else str(m.get("salary", 0))
        lines.append(f"- 薪資下限: {salary_text}")
        lines.append(f"- 分數: {m['score']}")
        lines.append(f"- 理由: {'; '.join(m['reasons'])}")
        if m["url"]:
            lines.append(f"- 連結: {m['url']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_line_text(matched: list[dict[str, Any]], date_str: str) -> str:
    lines = [f"104 每日職缺 ({date_str})"]
    if not matched:
        lines.append("今天沒有符合條件的職缺。")
        return "\n".join(lines)
    for i, m in enumerate(matched, 1):
        lines.append(f"{i}. {m['title'][:40]}")
        lines.append(f"   公司: {m.get('company', '') or '未提供'}")
        salary_text = "面議" if int(m.get("salary", 0)) <= 0 else str(m.get("salary", 0))
        lines.append(f"   薪資: {salary_text}")
        keyword_hits = [
            r.split(":", 1)[1].strip()
            for r in m.get("reasons", [])
            if r.startswith("關鍵字符合:")
        ]
        if keyword_hits:
            lines.append(f"   關鍵字: {', '.join(keyword_hits[:8])}")
        if m.get("score") is not None:
            lines.append(f"   分數: {m['score']}")
        if m.get("url"):
            lines.append(f"   {m['url']}")
    text = "\n".join(lines)
    return text[:4500]


def minimize_job_output(job: dict[str, Any]) -> dict[str, Any]:
    raw_salary = job.get("salary", 0)
    try:
        salary_num = int(raw_salary or 0)
    except (TypeError, ValueError):
        salary_num = 0
    return {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "city": job.get("city", ""),
        "salary": "面議" if salary_num <= 0 else salary_num,
        "url": job.get("url", ""),
        "score": job.get("score", 0),
        "reasons": job.get("reasons", []),
    }


def canonical_job_key(job: dict[str, Any]) -> str:
    url = str(job.get("url", "")).strip()
    if url:
        return url.split("?", 1)[0].rstrip("/")
    title = str(job.get("title", "")).strip().lower()
    company = str(job.get("company", "")).strip().lower()
    return f"{title}::{company}"


def load_seen_job_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return keys


def save_seen_job_keys(path: Path, keys: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(sorted(keys)) + ("\n" if keys else "")
    path.write_text(content, encoding="utf-8")


def push_line_message(text: str) -> tuple[bool, str]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    to_user_id = os.getenv("LINE_TO_USER_ID", "").strip()
    endpoint = os.getenv("LINE_PUSH_ENDPOINT", "https://api.line.me/v2/bot/message/push")
    timeout = int(os.getenv("LINE_TIMEOUT", "20"))

    if not token or not to_user_id:
        return False, "略過：LINE token 或 userId 未設定"
    if len(token) < 80:
        return False, "失敗：LINE token 長度異常，請使用 Messaging API Channel access token"
    if not (to_user_id.startswith("U") and len(to_user_id) >= 20):
        return False, "失敗：LINE_TO_USER_ID 格式異常，通常需以 U 開頭"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    # Validate token first for clearer error.
    info_resp = requests.get(
        "https://api.line.me/v2/bot/info", headers=headers, timeout=timeout
    )
    if info_resp.status_code != 200:
        return (
            False,
            f"失敗：LINE token 驗證失敗（status={info_resp.status_code}）",
        )
    payload = {
        "to": to_user_id,
        "messages": [{"type": "text", "text": text}],
    }
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        return False, f"失敗：LINE push 回應 status={resp.status_code}"
    return True, "成功：LINE 推播已送出"


def append_google_sheet_rows(matched: list[dict[str, Any]], date_str: str) -> bool:
    credentials_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "").strip()
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
    worksheet_name = os.getenv("GOOGLE_SHEETS_WORKSHEET", "jobs").strip()
    header_row_raw = os.getenv("GOOGLE_SHEETS_HEADER_ROW", "auto").strip()
    append_header = os.getenv("GOOGLE_SHEETS_APPEND_HEADER", "true").strip().lower() == "true"
    create_if_missing = (
        os.getenv("GOOGLE_SHEETS_CREATE_WORKSHEET_IF_MISSING", "false").strip().lower()
        == "true"
    )

    if not credentials_file or not spreadsheet_id:
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Google Sheets 套件，請先 pip install -r requirements.txt"
        ) from exc

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        if not create_if_missing:
            raise RuntimeError(
                f"找不到既有工作表: {worksheet_name}，請確認 GOOGLE_SHEETS_WORKSHEET"
            )
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)

    default_header = [
        "date",
        "title",
        "company",
        "city",
        "salary",
        "score",
        "reasons",
        "url",
        "source",
    ]
    known_header_aliases = {
        "date",
        "日期",
        "title",
        "職缺名稱",
        "job_title",
        "company",
        "公司",
        "company_name",
        "city",
        "地點",
        "location",
        "salary",
        "薪資",
        "score",
        "分數",
        "reasons",
        "理由",
        "url",
        "連結",
        "link",
        "source",
        "來源",
    }

    def detect_header_row() -> int:
        if header_row_raw and header_row_raw.lower() != "auto":
            try:
                row_num = int(header_row_raw)
                return max(1, row_num)
            except ValueError:
                return 1
        # Auto-detect header row from top 5 rows by matched known columns.
        best_row = 1
        best_score = -1
        for i in range(1, 6):
            vals = worksheet.row_values(i)
            score = sum(1 for v in vals if v.strip().lower() in known_header_aliases)
            if score > best_score:
                best_score = score
                best_row = i
        return best_row

    header_row = detect_header_row()
    first_row = worksheet.row_values(header_row)
    if not first_row:
        if not append_header:
            raise RuntimeError(f"工作表無欄位列，請先建立第 {header_row} 列欄位名稱")
        worksheet.update(values=[default_header], range_name=f"A{header_row}:I{header_row}")
        first_row = default_header
    else:
        # Use only contiguous header cells from the beginning to avoid
        # accidental KPI/summary cells in later columns being treated as headers.
        trimmed: list[str] = []
        for cell in first_row:
            if not cell.strip():
                break
            trimmed.append(cell)
        if trimmed:
            first_row = trimmed

    def pick_value(job: dict[str, Any], col_name: str) -> str:
        key = col_name.strip().lower()
        reasons_text = "; ".join(job.get("reasons", []))
        raw_salary = job.get("salary", 0)
        try:
            salary_num = int(raw_salary or 0)
        except (TypeError, ValueError):
            salary_num = 0
        salary_text = "面議" if salary_num <= 0 else str(raw_salary)
        mapping = {
            "date": date_str,
            "日期": date_str,
            "title": str(job.get("title", "")),
            "職缺名稱": str(job.get("title", "")),
            "job_title": str(job.get("title", "")),
            "company": str(job.get("company", "")),
            "公司": str(job.get("company", "")),
            "company_name": str(job.get("company", "")),
            "city": str(job.get("city", "")),
            "地點": str(job.get("city", "")),
            "location": str(job.get("city", "")),
            "salary": salary_text,
            "薪資": salary_text,
            "score": str(job.get("score", 0)),
            "分數": str(job.get("score", 0)),
            "reasons": reasons_text,
            "理由": reasons_text,
            "url": str(job.get("url", "")),
            "連結": str(job.get("url", "")),
            "link": str(job.get("url", "")),
            "source": "https://www.104.com.tw/jobs/search/",
            "來源": "https://www.104.com.tw/jobs/search/",
            "投遞": "未投遞",
            "開信": "FALSE",
            "回應": "FALSE",
            "面試": "FALSE",
            "offer": "FALSE",
        }
        return mapping.get(key, "")

    rows = []
    for job in matched:
        rows.append([pick_value(job, col) for col in first_row])

    if not rows:
        return True
    # NOTE:
    # append_rows uses the Sheets append API (insert rows). Manually calling add_rows
    # beforehand can create duplicated blank rows (e.g., +10 blank then +10 inserted rows).
    # Rely on append_rows to handle row growth.
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="104 每日職缺篩選工具")
    parser.add_argument(
        "--source",
        default="web104",
        choices=["web104", "api", "file"],
        help="資料來源: web104(104 公開搜尋) / api / file(本地測試)",
    )
    parser.add_argument("--rules", default="rules.json", help="篩選規則檔案")
    parser.add_argument("--output-dir", default="outputs", help="輸出資料夾")
    parser.add_argument(
        "--seen-file",
        default="outputs/seen_job_keys.txt",
        help="已處理職缺去重檔案（跨次執行）",
    )
    parser.add_argument(
        "--ignore-seen-dedup",
        action="store_true",
        help="一次性忽略歷史去重檔（僅本次執行）",
    )
    parser.add_argument("--input-file", default="sample_104_jobs.json", help="--source file 時使用")
    parser.add_argument(
        "--no-line-push", action="store_true", help="只輸出檔案，不推播 LINE"
    )
    args = parser.parse_args()

    rules_path = Path(args.rules)
    output_dir = Path(args.output_dir)
    seen_file = Path(args.seen_file)
    output_dir.mkdir(parents=True, exist_ok=True)

    rules = load_rules(rules_path)
    if args.source == "web104":
        raw_jobs = fetch_jobs_from_104_web()
        jobs = [normalize_job(j) for j in raw_jobs]
    elif args.source == "file":
        jobs = fetch_jobs_from_file(Path(args.input_file))
        raw_jobs = jobs
    else:
        raw_jobs = fetch_jobs()
        jobs = [normalize_job(j) for j in raw_jobs]

    # Remove duplicates in the same run.
    deduped_jobs: list[dict[str, Any]] = []
    run_seen_keys: set[str] = set()
    for job in jobs:
        key = canonical_job_key(job)
        if key in run_seen_keys:
            continue
        run_seen_keys.add(key)
        deduped_jobs.append(job)
    jobs = deduped_jobs

    # Remove jobs that were already surfaced in previous runs.
    historical_seen_keys = set()
    if not args.ignore_seen_dedup:
        historical_seen_keys = load_seen_job_keys(seen_file)
        jobs = [job for job in jobs if canonical_job_key(job) not in historical_seen_keys]

    matched: list[dict[str, Any]] = []
    for job in jobs:
        score, reasons = score_job(job, rules)
        if score < rules.minimum_score:
            continue
        job["score"] = score
        job["reasons"] = reasons
        matched.append(job)

    matched.sort(key=lambda x: x["score"], reverse=True)
    matched = matched[: rules.top_n]

    date_str = dt.date.today().isoformat()
    md_content = render_markdown(matched, date_str)
    minimized_jobs = [minimize_job_output(job) for job in matched]
    json_output = {
        "date": date_str,
        "source": "https://www.104.com.tw/jobs/search/",
        "usage_notice": "僅供個人求職整理，不對外提供 API 或下載。",
        "total_candidates": len(raw_jobs),
        "matched_count": len(minimized_jobs),
        "matched_jobs": minimized_jobs,
    }

    md_path = output_dir / f"jobs_{date_str}.md"
    json_path = output_dir / f"jobs_{date_str}.json"
    md_path.write_text(md_content, encoding="utf-8")
    json_path.write_text(
        json.dumps(json_output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.chmod(md_path, 0o600)
    os.chmod(json_path, 0o600)

    new_seen_keys = set(historical_seen_keys)
    for job in minimized_jobs:
        new_seen_keys.add(canonical_job_key(job))
    save_seen_job_keys(seen_file, new_seen_keys)

    print(f"完成: {md_path}")
    print(f"完成: {json_path}")
    if not args.no_line_push:
        line_text = build_line_text(matched, date_str)
        ok, msg = push_line_message(line_text)
        print(f"LINE 推播: {msg}")
    if append_google_sheet_rows(minimized_jobs, date_str):
        print("Google Sheet: 已嘗試寫入（若未設定 credentials/sheet id 則自動略過）")


if __name__ == "__main__":
    main()
