---
title: Apprise Admin Notifications
description: Configure optional admin and internal notifications through Apprise.
keywords: CiteGuild, Apprise, Slack, notifications, alerts
author: LVTD LLC
---

Apprise admin notifications are included because this project was generated with `use_apprise = y`.

The integration is runtime-opt-in: Django only sends admin notifications to Apprise when both `APPRISE_API_URL` and `APPRISE_CONFIG_KEY` are set. If Apprise is unset or unavailable, the helper falls back to email when `ADMIN_NOTIFICATION_EMAIL_FALLBACK=true`.

## What gets installed

- `apps.core.notifications.send_admin_notification(...)`
- Apprise API settings in Django
- `.env.example` entries for Apprise URL, saved config key, Basic Auth, payload format, timeout, and email fallback
- Tests covering Apprise delivery, Basic Auth, email fallback, and fallback-disable behavior

Use `send_admin_notification` for internal events like new project submissions, new paid leads, failed automation handoffs, or other alerts that operators should see quickly.

## Apprise setup

1. Deploy or choose an Apprise API instance.
2. Create a saved config key for this app, for example `citeguild`.
3. Add one or more notification targets to that key, such as Slack, Discord, email, PagerDuty, or webhooks.
4. If the Apprise API is protected with Basic Auth, keep those credentials in your production secret manager.

Set these on every Django process that can emit notifications, usually both web and worker containers/apps:

```env
APPRISE_API_URL=https://apprise.yourdomain.com
APPRISE_CONFIG_KEY=citeguild
APPRISE_BASIC_AUTH_USER=<basic auth user, if enabled>
APPRISE_BASIC_AUTH_PASSWORD=<basic auth password, if enabled>
APPRISE_NOTIFICATION_FORMAT=markdown
APPRISE_REQUEST_TIMEOUT=10
ADMIN_NOTIFICATION_EMAIL_FALLBACK=true
ADMIN_NOTIFICATION_EMAIL_RECIPIENTS=LVTD LLC <rasul@lvtd.dev>
```

`APPRISE_CONFIG_KEY` is the saved key used in Apprise's `/notify/{key}` endpoint. Do not put Slack bot tokens or webhook URLs directly in Django app env vars; store those inside Apprise.

## Usage

```python
from apps.core.notifications import send_admin_notification

send_admin_notification(
    "New project submitted",
    "A user submitted a new project for review.",
    notification_type="info",
)
```

`notification_type` maps to Apprise's supported message types: `info`, `success`, `warning`, and `failure`.

## Smoke test

Run this inside the deployed Django container after setting env vars and restarting:

```bash
python manage.py shell -c "from apps.core.notifications import send_admin_notification; print(send_admin_notification('Apprise smoke test', 'If you see this, Django → Apprise works.'))"
```

Expected output:

```text
apprise
```

If it prints `email`, Django is not seeing `APPRISE_API_URL` or `APPRISE_CONFIG_KEY`, or Apprise failed and email fallback handled the alert.

## Common gotchas

- **Wrong process:** Add the same Apprise env vars to workers if background jobs send notifications.
- **No restart:** Django reads settings at startup. Restart/redeploy after changing env vars.
- **Wrong key:** `APPRISE_CONFIG_KEY` must match the saved Apprise config key, not the Slack channel name.
- **Token leakage:** Keep Slack/webhook tokens in Apprise, not in Django/CapRover app env vars.
- **Fallback surprise:** Set `ADMIN_NOTIFICATION_EMAIL_FALLBACK=false` only when you want Apprise failures to raise exceptions instead of sending email.

## Disabling Apprise

Unset either value and restart the app:

```env
APPRISE_API_URL=
APPRISE_CONFIG_KEY=
```

The helper remains importable and will send email fallback notifications instead.
