# Product analytics

This project uses PostHog for consented product analytics. Browser capture is
opted out by default, DOM autocapture is disabled, and pageviews are emitted
manually only for the allowlisted marketing, auth, blog, and docs routes in
`apps/core/context_processors.py`.

## Privacy contract

- Never send passwords, form values, API keys, payment identifiers, full URLs,
  query strings, or private route parameters to PostHog.
- Browser events use normalized Django route templates. Referrers are reduced
  to their origin and domain.
- Campaign values are limited to `utm_source`, `utm_medium`, `utm_campaign`,
  `utm_content`, `utm_term`, and `campaign_id`. Advertising click IDs are
  removed.
- Authenticated browser and server events share the profile ID as their
  `distinct_id`. Server events include `event_version`, `environment`,
  `profile_id`, and `current_state`; they do not include email addresses.
- A visitor must choose **Allow analytics** before pageviews, page-leave
  signals, attribution, or lifecycle events are captured. Declining removes
  stored attribution.
- Logout resets the PostHog browser identity.

- AI observability is separately opt-in and exports performance metadata
  without prompt, response, tool, embedding input, binary, or exception
  contents.


- MCP analytics record protocol and tool usage, but replace argument values with
  argument names and coarse types, remove tool responses, and drop exception
  payloads.


## Attribution

The browser stores sanitized first-touch and latest-touch attribution for up to
180 days after consent. PostHog person properties use `first_touch_*` and
`current_touch_*` names. Untagged internal navigation does not erase the latest
campaign.

## Event contract

Event names are lowercase snake case and describe completed actions. The
starter includes:

- `citeguild_signup_completed`
- `citeguild_user_logged_in`
- `citeguild_account_deleted`
- `citeguild_checkout_started` when Stripe is enabled
- `citeguild_marketing_cta_clicked` for annotated calls
  to action

Add product-specific activation and retention events in
`apps/core/analytics.py`, and call `track_event()` only after the action has
succeeded. Keep properties bounded and avoid copying model fields wholesale.
Signup, checkout, and account deletion events flush the server SDK queue before
their worker finishes.

## PostHog project setup

- Send browser and server events to the same PostHog project.
- Set `POSTHOG_BROWSER_HOST` to a first-party reverse proxy in production when
  possible. It must forward PostHog ingestion and static asset paths without
  caching ingestion responses.
- Keep `POSTHOG_HOST` on the regional PostHog ingestion endpoint for server
  capture.

- When both PostHog and Pydantic AI are generated, set
  `POSTHOG_AI_OBSERVABILITY_ENABLED=True` to instrument agents and embedders
  without recording model content.


- MCP usage tracking is enabled automatically when `POSTHOG_API_KEY` is set.
  The ASGI lifespan drains pending MCP events during graceful shutdown.

- Exclude non-production and staff traffic before using dashboards for product
  or marketing decisions.
- Validate one unique UTM through consent and signup before launching paid
  acquisition.
