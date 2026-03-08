# WIP Notes

## Current Status

- 104 / Cake crawler 已完成並已推上 `main`
- GitHub Actions 已可同時跑 104 + Cake
- Google credentials 已整理到：
  - `/Users/wendy/.config/codex/google/google-service-account.json`
  - `/Users/wendy/.config/codex/google/google-oauth-client.json`
  - `/Users/wendy/.config/codex/google/google-drive-token.json`
- Cover letter / Drive integration 尚未完成，不在 `main`

## WIP Files

- `scripts/apply_test.py`
- `scripts/generate_cover_letters_drive.py`
- `requirements.txt`

## Intentionally Local Only

- `.browser_profiles/`
- OAuth client / token files
- shared credentials under `~/.config/codex/google/`

## Current Findings

- PDF resume parsing 品質差，不適合作為主要來源
- `Resume_BeiYu_Wang.md` 已建立並上傳到 Google Drive
- OAuth 已可存取個人 Google Drive
- Drive 子資料夾建立與檔案寫入可行
- Cover letter 內容品質仍需調整，不適合全面生成
- 104 / Cake 自動投遞流程尚未穩定，先不要繼續往 submit automation 推進

## Recent Decisions

- 104 預設抓取頁數改為 `WEB104_PAGES=3`（程式預設值），手動擴搜時可暫時用 `5` 頁。
- 104 規則目前保留較乾淨的版本：`require_industry_match=true`、`top_n=50`。
- `.browser_profiles/` 已加入 `.gitignore`，維持 local only，不應提交。
- GitHub push 目標預設使用 `sheruwen`。
- 這台機器若直接 `git push` 仍被 `osxkeychain` 干擾，可用一次性命令強制走 GitHub CLI 認證：
  - `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`

## Latest Update (2026-03-08)

- `wip/job-search-tuning` 已合併並推上 `main`。
- GitHub repo secret `WEB104_PAGES` 已更新（由使用者在 GitHub 端操作）。
- Cake 抓取改為 Playwright 優先、requests fallback；`CAKE_PAGES=3` 測試時可抓到 `30` 筆原始候選（先前常見為 `10` 筆）。
- 104 / Cake 抓取層已支援多關鍵字：
  - `WEB104_KEYWORDS`（優先於 `WEB104_KEYWORD`）
  - `CAKE_KEYWORDS`（優先於 `CAKE_KEYWORD`）
- 規則檔已加入 `Project Manager` / `Software Project Manager` / `專案經理`，擴充 PM 類職缺範圍。
- 多關鍵字測試結果（不回寫正式 seen）：
  - 104：`total_candidates=384`、`matched_count=50`
  - Cake：`total_candidates=75`、`matched_count=15`
- 測試去重檔建議使用：
  - 104: `/tmp/seen_104_job_keys.txt`
  - Cake: `/tmp/seen_cake_job_keys.txt`

## Next Step

1. 以文字版履歷（md / Google Doc）作為唯一來源
2. 只重跑前 2 筆職缺的 cover letter
3. 先優化模板與內容品質，再擴大到全部職缺

## Resume / Template Drive IDs

- Resume md: `18cjX8Kez2pCywcGg7jP5PyjTnJaIYQ3L`
- Cover Letter CN: `1hwOQ68gSjz4dvZpx1hPYDD4rKlNu03QJ6slbv5MfyBk`
- Cover Letter EN: `1K0NwmWofNC-zgiNCQKQuu9qxhB4Zk1m3BhjmuiKJzMQ`
- Parent folder: `19RrPAFDrwbrl6AzFjleEdOBI_gH4R3xZ`

## Branch Convention

- Keep this unfinished work on a local branch such as `wip/cover-letter-drive`
- Do not merge to `main` until content quality is acceptable
