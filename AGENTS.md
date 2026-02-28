# Project Notes

## WIP Continuation

If this project is being resumed mid-development, read `WIP_NOTES.md` first before making changes.

## Google Credentials Convention

For Google Drive / Google Sheets integration, reuse the shared machine-level credentials instead of storing project-specific copies.

See:
- `/Users/wendy/.config/codex/GOOGLE_SETUP.md`

Typical env vars:
- `GOOGLE_SHEETS_CREDENTIALS_FILE=/Users/wendy/.config/codex/google/google-service-account.json`
- `GOOGLE_OAUTH_CLIENT_FILE=/Users/wendy/.config/codex/google/google-oauth-client.json`
- `GOOGLE_OAUTH_TOKEN_FILE=/Users/wendy/.config/codex/google/google-drive-token.json`
