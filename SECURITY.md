# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Sensitive data this project handles

- **Plex token** - grants full access to your Plex account; stored in `.env` or `data/plex_token`
- **YouTube OAuth token** - grants upload access to your YouTube account; stored in `data/youtube_token.json`
- **YouTube OAuth credentials** - client ID and secret from Google Cloud Console; stored in `data/youtube_credentials.json` or passed via env vars

None of these files are ever committed to the repository. `.env`, `data/`, and credential files are listed in `.gitignore`.

## Reporting a vulnerability

Do not open a public issue for security vulnerabilities.

Email **contact@replaytagger.com** with:
- A description of the vulnerability
- Steps to reproduce
- Potential impact

You will receive a response within 72 hours. If the issue is confirmed, a fix will be released as soon as possible and you will be credited in the changelog unless you prefer otherwise.
