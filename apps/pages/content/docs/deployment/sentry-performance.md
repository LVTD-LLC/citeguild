---
title: Sentry Performance Monitoring
description: Use Sentry traces, profiling, logs, and dashboards to analyze slow Django page loads.
keywords: CiteGuild, Sentry, performance, tracing, profiling, dashboard
author: LVTD LLC
---

Sentry is included because this project was generated with `use_sentry = y`.

The starter configures backend Django observability. It cannot create a dashboard inside your Sentry organization because that needs your Sentry org slug, project slug, region, and an API token. Use the prompt below with an AI agent that has access to your Sentry account or Sentry API token.

## What to use for slow pages

Use Sentry traces as the first signal for slow server-rendered pages. A trace shows the Django request transaction plus database, cache, middleware, Redis, and other spans around it.

Use profiling when a trace points to Python CPU time. Profiling is enabled with `profile_lifecycle="trace"` and `SENTRY_PROFILE_SESSION_SAMPLE_RATE`, so profiles are collected while sampled spans are active.

Use logs for context around a slow request or error. This project keeps breadcrumb/event/log levels separate so logs can help debugging without turning every info log into searchable Sentry log volume.

Use custom metrics only when you have a product-specific KPI or SLO to track. For generic page-load optimization, traces and profiling are more useful than counters.

## Baseline checklist

1. Set `SENTRY_DSN` in the deployed web and worker environments.
2. Keep `SENTRY_RELEASE` tied to the deployed commit SHA when your platform supports it.
3. Leave `SENTRY_TRACES_SAMPLE_RATE=1.0` temporarily if traffic is modest and you need a clean baseline.
4. Reduce `SENTRY_TRACES_SAMPLE_RATE` after the baseline if traffic is high.
5. Keep `SENTRY_BACKGROUND_TRACES_SAMPLE_RATE` lower than the web rate unless worker performance is the current investigation.
6. Open Sentry and inspect the slow page's transaction under Traces/Performance before changing code.
7. After optimization, compare the same transaction's p50, p75, p95, throughput, and slowest spans before and after the release.

The sampler drops healthcheck, static, media, favicon, and robots transactions so the dashboard stays focused on real application page loads.

## Recommended dashboard

Create a dashboard for page loads with widgets like:

- p50, p75, and p95 transaction duration grouped by transaction name.
- Slowest transactions by p95 duration.
- Request throughput grouped by transaction name.
- Error count or error rate grouped by transaction name.
- Slowest spans for the page you are optimizing, especially database and cache spans.
- Release comparison for the transaction before and after an optimization deploy.

For server-rendered Django pages, backend request duration is usually the most actionable first dashboard. If you need browser page-load timing, Web Vitals, replay, or frontend route changes, add the Sentry Browser SDK separately and connect it to the same release/environment.

## Prompt for an AI agent

```text
Create or update a Sentry dashboard for CiteGuild page-load performance.

Context:
- This is a Django app using Sentry Python SDK.
- Backend traces are enabled through SENTRY_DSN, traces_sampler, DjangoIntegration middleware/cache spans, RedisIntegration, profiling with profile_lifecycle="trace", and structured logs.
- Healthcheck, static, media, favicon, and robots transactions should be ignored.
- Use release and environment filters so we can compare before/after deploys.

What I need:
1. Inspect the Sentry org/project and find the correct project slug and available transaction names.
2. Create a dashboard named "Page Load Performance".
3. Add widgets for p50, p75, and p95 transaction duration by transaction; slowest transactions; throughput by transaction; error count or error rate by transaction; and slowest DB/cache spans for the pages with the highest p95.
4. Add a focused widget for the homepage or primary landing page transaction if it exists.
5. Do not hardcode or commit Sentry API tokens. Use environment variables or the connected Sentry integration.
6. If browser page-load metrics are required and the app does not have Sentry Browser SDK installed, propose the smallest follow-up change with masked replay defaults and trace propagation to the Django site URL.
7. Return the dashboard URL, the transaction names found, and the exact filters/time range used for the baseline.
```

## Useful references

- [Sentry Python Django integration](https://docs.sentry.io/platforms/python/integrations/django/)
- [Sentry Python tracing](https://docs.sentry.io/platforms/python/tracing/)
- [Sentry Python profiling](https://docs.sentry.io/platforms/python/profiling/)
- [Sentry Python logs](https://docs.sentry.io/platforms/python/logs/)
