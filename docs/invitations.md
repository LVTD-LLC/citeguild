# Free, invitation-only membership

Registration requires an existing active member's invitation code or link. Each
member gets one stable reusable invitation in Settings, created on first visit.
Codes are random UUIDs, unique in the database, and unrelated to API credentials.
An invitation is invalid when its owner is disabled or deleted. Existing accounts
need no invitation and no payment. Operators can still pause all new registrations
with `ALLOW_SIGNUPS=False`; this does not block existing logins.

Password and passkey forms validate codes; persistence adapters enforce the same
requirement. Opening an invite link stores its code in the server session so it
survives switching to passkey signup or a social provider redirect. Social signup
without a valid invitation is blocked, including automatic account creation.
Existing social login and account connection are unchanged. Email verification
remains mandatory. Invitations confer no ownership of the inviter's sites.

Active accounts may submit/manage sites and search via API, CLI, and MCP without
Stripe status checks. Disabled users and suspended projects remain excluded from
indexing and retrieval. Billing status fields in existing APIs remain billing
facts, not membership/access flags. Stripe webhooks and the billing portal remain
for legacy subscriptions; new checkout attempts redirect to the dashboard without
calling Stripe. This deployment does not itself cancel subscriptions or issue
refunds. Such billing changes require a separate operator action.
