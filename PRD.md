# Career Bot PRD

## 1. Product Overview
- Product name: Career Bot
- Goal: Automatically fetch and filter 104 job postings, then push qualified jobs to LINE and append records to Google Sheet.
- Primary users: Individual job seeker (owner/operator of this repository).

## 2. Problem Statement
- Manual job searching and tracking is repetitive.
- Important roles may be missed without frequent checks.
- Repeated jobs and scattered records reduce decision quality.

## 3. Objectives
- Fetch jobs automatically on schedule.
- Filter with configurable rules and scoring.
- Push concise daily results to LINE.
- Persist records to Google Sheet for tracking.
- Reduce duplicate notifications across runs.

## 4. Non-Goals
- Public API service.
- Multi-tenant user system.
- External-facing dashboard.

## 5. User Stories
- As a job seeker, I want daily filtered jobs delivered to LINE, so I can review quickly.
- As a job seeker, I want rule-based filtering, so only relevant PM roles are surfaced.
- As a job seeker, I want historical records in Google Sheet, so I can track actions over time.
- As a job seeker, I want duplicate jobs suppressed, so I do not receive repeated noise.

## 6. Functional Requirements
- FR-1: The system shall fetch jobs from 104 search API endpoint.
- FR-2: The system shall evaluate jobs with rules from `rules.json`.
- FR-3: The system shall output daily artifacts in `outputs/` as Markdown and JSON.
- FR-4: The system shall push summary text to LINE when credentials exist.
- FR-5: The system shall append matched jobs to configured Google Sheet.
- FR-6: The system shall deduplicate jobs within a run and across runs.
- FR-7: The system shall support manual trigger (`workflow_dispatch`) and scheduled trigger (`schedule`).

## 7. Non-Functional Requirements
- NFR-1: Workflow should complete within 20 minutes.
- NFR-2: Secrets must be stored in GitHub Secrets (no hardcoded credentials).
- NFR-3: Job output files should use restricted permissions where applicable.
- NFR-4: Failures should be observable through GitHub Actions logs.

## 8. Configuration
- Runtime: Python 3.12 (GitHub Actions), local Python 3.x.
- Dependencies: `requests`, `gspread`, `google-auth`.
- Rule config: `rules.json`.
- Workflow: `.github/workflows/daily-job.yml`.

## 9. Schedule and Operations
- Current schedule: once daily at 10:00 Asia/Taipei (`cron: "0 2 * * *"` in UTC).
- Backup trigger: `repository_dispatch` with event `cron-fallback`.

## 10. Success Metrics
- % of runs completed successfully.
- Number of matched jobs/day (stable and relevant range).
- Duplicate notification rate (target: near 0 across runs).
- Manual review time saved per day.

## 11. Risks and Mitigations
- Risk: GitHub scheduled jobs are delayed/skipped.
  - Mitigation: keep `repository_dispatch` fallback.
- Risk: Duplicate jobs due to URL variants.
  - Mitigation: canonical job key normalization and persisted seen keys.
- Risk: Secret misconfiguration.
  - Mitigation: startup validation and explicit warning logs.

## 12. Open Questions
- Should dedup history expire after N days to re-surface long-open roles?
- Should push message include direct apply status fields?
- Should Google Sheet row schema be versioned?

## 13. Change Log
- Rule: every project adjustment must be recorded here.
- Entry format:
  - Date (YYYY-MM-DD)
  - Change summary
  - Files changed
  - Reason
  - Owner

### 2026-02-20
- Change summary: Added cross-run dedup persistence in GitHub Actions and strengthened canonical dedup key for 104 links.
- Files changed: `.github/workflows/daily-job.yml`, `job_tool.py`
- Reason: Prevent repeated push notifications across workflow runs.
- Owner: Wendy / Codex

### 2026-02-20
- Change summary: Updated workflow schedule to run once daily at 10:00 Asia/Taipei.
- Files changed: `.github/workflows/daily-job.yml`
- Reason: Replace high-frequency test schedule with production cadence.
- Owner: Wendy / Codex

### PRD Log Automation
- Helper script: `scripts/add_prd_change.sh`
- Command:
  - `bash scripts/add_prd_change.sh "<change summary>" "<files changed>" "<reason>" "<owner>"`

### 2026-02-20
- Change summary: Added PRD change-log helper script to standardize future update records.
- Files changed: `scripts/add_prd_change.sh`, `PRD.md`
- Reason: Ensure every project adjustment is recorded consistently in PRD.
- Owner: Wendy / Codex
