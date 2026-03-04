# Project Notes

## Global Preferences

Follow the global preferences in:
- `/Users/wendy/.config/codex/PREFERENCES.md`

If there is any conflict or ambiguity, ask before executing.

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

## GitHub Push Convention

- Default GitHub push identity on this machine should be `sheruwen`.
- For account switching, use `gh auth switch -u sheruwen` or another explicit account before pushing if needed.
