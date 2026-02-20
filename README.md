# 104 每日職缺清單工具（104 公開搜尋 + LINE 推播）

這個工具會：
1. 直接抓取 104 公開搜尋職缺。
2. 用 `rules.json` 的條件評分與篩選職缺。
3. 每次輸出當日結果到 `outputs/jobs_YYYY-MM-DD.md` 與 `outputs/jobs_YYYY-MM-DD.json`。
4. 把摘要推播到你的 LINE。
5. 自動把當日職缺 append 到 Google Sheet。

## 1) 初始化

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp rules.example.json rules.json
```

## 2) 設定

編輯 `.env`：
- `WEB104_KEYWORD`: 搜尋關鍵字（例如 `產品經理`）
- `WEB104_AREA`: 地區代碼（例如 `6001001000` 代表台北市）
- `WEB104_PAGES`: 要抓幾頁搜尋結果
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Messaging API token
- `LINE_TO_USER_ID`: 要推播的 LINE 使用者 ID
- `GOOGLE_SHEETS_CREDENTIALS_FILE`: service account JSON 絕對路徑
- `GOOGLE_SHEETS_SPREADSHEET_ID`: Google Sheet ID
- `GOOGLE_SHEETS_WORKSHEET`: 工作表名稱（預設 `Job List`）
- `GOOGLE_SHEETS_HEADER_ROW`: 欄位列號（預設 `auto`，自動判斷表頭列）
- `GOOGLE_SHEETS_CREATE_WORKSHEET_IF_MISSING`: 是否允許自動建新分頁（預設 `false`）

編輯 `rules.json` 以符合你的求職條件。
常用欄位：
- `include_keywords`: 命中可加分
- `require_include_keyword_match`: 是否要求至少命中一個 include 關鍵字
- `required_keywords_all`: 每一個都必須命中
- `required_keyword_groups`: 每一組同義詞至少命中一個
- `min_required_group_matches`: 需要命中的群組數（例如 `2` 代表四組中中兩組即可）
- `exclude_keywords`: 命中就排除
- `include_companies` / `exclude_companies`: 公司白名單加分、黑名單排除
- `include_industry_keywords`: 產業關鍵字（例如軟體、SaaS、雲端）
- `require_industry_match`: 是否改成硬篩選目標產業
- `allowed_cities`: 城市硬篩選
- `preferred_cities`: 城市加分
- `minimum_salary`: 最低薪資門檻（薪資未知不扣分）
- `minimum_score`: 最低分數門檻

## 3) 手動執行

```bash
bash run_daily.sh
```

如果你想先不推播 LINE，只輸出檔案：

```bash
python3 job_tool.py --no-line-push
```

如果你要先做離線測試（不連外部來源）：

```bash
python3 job_tool.py --source file --input-file sample_104_jobs.json --no-line-push
```

如果你要一次性忽略歷史去重（本次可重複寫入）：

```bash
python3 job_tool.py --source web104 --no-line-push --ignore-seen-dedup
```

## 4) LINE 設定（一次性）

1. 在 LINE Developers 建立 Messaging API channel。  
2. 到 channel 設定頁產生 `Channel access token`。  
3. 把 Bot 加為好友。  
4. 取得 `userId`：先啟用 webhook，傳一則訊息給 Bot，從 webhook event payload 取 `source.userId`。  
5. 將 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_TO_USER_ID` 填進 `.env`。

## 5) 每天自動執行（macOS / Linux cron）

先給執行權限：

```bash
chmod +x run_daily.sh
```

打開 crontab：

```bash
crontab -e
```

加入這行（每天早上 9:00）：

```cron
0 9 * * * /Users/wendy/wendy's\ projects/job\ application/run_daily.sh >> /Users/wendy/wendy's\ projects/job\ application/outputs/cron.log 2>&1
```

## 6) 雲端排程（GitHub Actions，電腦關機也可跑）

專案已內建 workflow：`/Users/wendy/wendy's projects/job application/.github/workflows/daily-job.yml`  
目前測試設定為每 5 分鐘執行一次（GitHub Actions 最小間隔）。
若 GitHub `schedule` 偶發漏觸發，可改用 `repository_dispatch` 當 fallback。

### GitHub Secrets 要設定的欄位

到 GitHub Repo -> `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`，新增：

- `WEB104_API_URL`（建議：`https://www.104.com.tw/jobs/search/api/jobs`）
- `WEB104_KEYWORD`
- `WEB104_AREA`
- `WEB104_PAGES`
- `WEB104_ORDER`
- `WEB104_ASC`
- `WEB104_TIMEOUT`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_TO_USER_ID`
- `LINE_PUSH_ENDPOINT`（建議：`https://api.line.me/v2/bot/message/push`）
- `LINE_TIMEOUT`
- `GOOGLE_SHEETS_SPREADSHEET_ID`
- `GOOGLE_SHEETS_WORKSHEET`
- `GOOGLE_SHEETS_APPEND_HEADER`
- `GOOGLE_SHEETS_CREATE_WORKSHEET_IF_MISSING`
- `GOOGLE_SHEETS_HEADER_ROW`
- `GOOGLE_SHEETS_CREDENTIALS_JSON_B64`（把 service account JSON 檔案做 base64 後貼上）

### 產生 `GOOGLE_SHEETS_CREDENTIALS_JSON_B64`

在本機執行：

```bash
base64 -i /absolute/path/to/google_service_account.json | tr -d '\n'
```

把輸出整串字串貼到 GitHub Secret `GOOGLE_SHEETS_CREDENTIALS_JSON_B64`。

### 手動觸發測試

GitHub Repo -> `Actions` -> `Daily Job Fetch` -> `Run workflow`。

### 排程備援（建議）

如果你發現 `schedule` 沒有固定觸發，可用外部 cron 服務（例如 cron-job.org）呼叫：

```bash
POST https://api.github.com/repos/sheruwen/career-bot/dispatches
Authorization: Bearer <GITHUB_PAT_WITH_repo_and_workflow>
Accept: application/vnd.github+json
Content-Type: application/json

{"event_type":"cron-fallback"}
```

這會觸發同一個 workflow（`repository_dispatch`）。

## 備註

- 預設 `--source web104`（104 公開搜尋），不需要 104 access token。
- 若未來你有 104 API，也可以改成 `python3 job_tool.py --source api`。
- 本工具輸出欄位採最小化（職缺名稱、公司、地點、薪資、連結、分數、理由）。
- 輸出檔案權限為 `600`（僅檔案擁有者可讀寫）。
- 使用情境定位為個人求職整理，不對外提供 API 或下載。
- 內建跨次去重，已處理職缺會記錄在 `outputs/seen_job_keys.txt`。
- Google Sheet 寫入使用 append API，由 API 處理插入列，避免先擴列再插入造成空白列。

## 評分邏輯（簡版）

系統分成三步驟：

1. 硬性篩選（不符合就淘汰）
- 命中 `exclude_keywords`
- 不符合 `required_keyword_groups` + `min_required_group_matches`
- 不在 `allowed_cities`
- 命中 `exclude_companies`
- 若 `require_industry_match=true` 且非目標產業

2. 分數計算（只對通過硬篩的職缺）
- 每命中一個 `include_keywords`：`+10`
- 命中目標產業關鍵字：`+8`
- 命中 `include_companies`：`+8`
- 命中 `preferred_cities`：`+6`
- 薪資 `>= minimum_salary`：`+6`
- 薪資 `< minimum_salary`：`-4`
- 薪資未知：不加不扣
- 若 `require_remote=true`：
  - 支援遠端：`+5`
  - 不支援遠端：`-8`

3. 產出結果
- 只保留 `score >= minimum_score`
- 依分數排序後取前 `top_n`（例如 10 筆）
- 預設啟用跨次去重（可用 `--ignore-seen-dedup` 單次略過）

## Google Sheet 設定（一次性）

1. 到 Google Cloud 建立專案並啟用 Google Sheets API。
2. 建立 Service Account，下載 JSON 金鑰檔。
3. 建立你的 Google Sheet，將該 Service Account Email 設為可編輯者。
4. 從 Sheet URL 取得 `SPREADSHEET_ID`（`/d/{id}/edit` 的 `{id}`）。
5. `.env` 填入：
   - `GOOGLE_SHEETS_CREDENTIALS_FILE`
   - `GOOGLE_SHEETS_SPREADSHEET_ID`
   - `GOOGLE_SHEETS_WORKSHEET`（例如 `Job List`）
   - `GOOGLE_SHEETS_HEADER_ROW=auto`（或手動指定 `2`）
   - `GOOGLE_SHEETS_CREATE_WORKSHEET_IF_MISSING=false`（只寫入既有分頁）

## 變數安全檢查（不讀密鑰內容）

可以用下面指令檢查 `.env` 必要欄位是否有填，並確認金鑰檔路徑是否存在。  
這個檢查只驗證「路徑與欄位狀態」，不會打開 JSON 密鑰檔內容。

```bash
cd "/Users/wendy/wendy's projects/job application"
python3 - <<'PY'
from pathlib import Path

env_path = Path('.env')
if not env_path.exists():
    print("NO_ENV_FILE")
    raise SystemExit(0)

keys = [
    "WEB104_API_URL",
    "WEB104_KEYWORD",
    "WEB104_AREA",
    "WEB104_PAGES",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_TO_USER_ID",
    "GOOGLE_SHEETS_CREDENTIALS_FILE",
    "GOOGLE_SHEETS_SPREADSHEET_ID",
    "GOOGLE_SHEETS_WORKSHEET",
]

vals = {}
for line in env_path.read_text(encoding='utf-8').splitlines():
    s = line.strip()
    if not s or s.startswith('#') or '=' not in s:
        continue
    k, v = s.split('=', 1)
    vals[k.strip()] = v.strip()

for k in keys:
    v = vals.get(k, "")
    ok = bool(v)
    extra = ""
    if k == "GOOGLE_SHEETS_CREDENTIALS_FILE" and ok:
        p = Path(v).expanduser()
        extra = f" path_exists={p.exists()} is_file={p.is_file()}"
    print(f"- {k}: set={ok}{extra}")
PY
```

## Git 安全檢查（推送前）

推送到 GitHub 前，先執行：

```bash
cd "/Users/wendy/wendy's projects/job application"
./scripts/check_git_safety.sh
```

這個檢查會阻擋以下檔案被追蹤：
- `.env` 正式密鑰檔
- `google-sheet-writer.json` 與其他 credentials/service-account JSON
- `keys/` 下的金鑰
- `.pem` / `.key`
