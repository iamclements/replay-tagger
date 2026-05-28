---
name: Bug report
about: Something is broken or behaving unexpectedly
title: '[BUG] '
labels: 'bug'
assignees: ''
---

**Describe the bug**
A clear description of what went wrong.

**To reproduce**
Steps to reproduce:
1. ...
2. ...

**Expected behavior**
What should have happened.

**Logs**
Paste the relevant log output. Set `LOG_FORMAT=text` in `.env` for readable output, or paste the JSON lines as-is.

```
paste logs here
```

**Environment**
- Deployment: Docker / bare Python
- OS / platform: e.g. Unraid 6.12, Synology DSM 7, Ubuntu 22.04
- ReplayTagger version: e.g. v2.2.0 (check `docker inspect` image tag or `replaytagger --version`)
- Plex Media Server version:
- ffmpeg version (`ffmpeg -version`):

**Config**
Paste your `config.yaml` (redact any tokens):

```yaml
paste config here
```

**Additional context**
Anything else that might be relevant.
