# Launch readiness and operator handoff

This is the day-one operating contract for CiteGuild's agent interfaces. The
CLI is tracked independently under CG-022 and does not change launch authority.
A public announcement is a separate, explicit decision for Rasul; completing
this checklist does not authorize one.

## Decision and ownership

Current decision: **no-launch pending CG-034 completion**. The production service
is healthy and paid API/MCP flows work, but the named Scribe editorial handoff and
the final dogfood citation edge still need evidence. CG-022 remains independent
from that editorial launch decision.

| Area | Primary | Backup or escalation |
| --- | --- | --- |
| Public launch, pricing, and policy decision | Rasul | Greg |
| Customer support, abuse intake, and daily metric review | Greg | Rasul |
| Releases, application incidents, backups, and recovery | Forge | Greg coordinates customer communication |
| Editorial relevance and publication approval | Scribe or the site's normal editor | Rasul |

Support and privacy requests go to `rasul@lvtd.dev`. Operators record incidents
and launch evidence without copying credentials, article bodies, search queries,
or private provider responses into tickets or chat.

## Evidence-linked launch checklist

- [x] Runtime configuration contracts: CG-006, PR
  [#9](https://github.com/LVTD-LLC/citeguild/pull/9).
- [x] One active $10 monthly Stripe plan and normalized webhook lifecycle:
  PRs [#10](https://github.com/LVTD-LLC/citeguild/pull/10) and
  [#11](https://github.com/LVTD-LLC/citeguild/pull/11). Production verification
  on 2026-08-02 found an active $10 USD monthly price, active CiteGuild product,
  enabled webhook, billing enabled, and signups open.
- [x] Sitemap-only ingestion, SSRF boundary, extraction, lifecycle, indexing,
  API, MCP, reconciliation, and detected graph: PRs
  [#15](https://github.com/LVTD-LLC/citeguild/pull/15) through
  [#30](https://github.com/LVTD-LLC/citeguild/pull/30); CG-022 separately owns
  CLI distribution over the completed v1 API.
- [x] Owner dashboard and activity: PR
  [#31](https://github.com/LVTD-LLC/citeguild/pull/31).
- [x] Paid-to-citation and unit-cost event contract: PR
  [#32](https://github.com/LVTD-LLC/citeguild/pull/32) and
  `docs/analytics/funnel-events.md`.
- [x] Real PostgreSQL, Redis, and Qdrant acceptance lane: PR
  [#33](https://github.com/LVTD-LLC/citeguild/pull/33).
- [x] Production topology, immutable rollout, and exact-release gate: PRs
  [#35](https://github.com/LVTD-LLC/citeguild/pull/35),
  [#36](https://github.com/LVTD-LLC/citeguild/pull/36), and
  [#37](https://github.com/LVTD-LLC/citeguild/pull/37).
- [x] Encrypted backups, alerts, restore, and Qdrant rebuild: PR
  [#39](https://github.com/LVTD-LLC/citeguild/pull/39). Snapshot `a29af01e`
  passed integrity verification and an isolated restore/rebuild drill in 25s.
- [x] Authenticated multi-call MCP reliability and large-crawl refill fixes:
  PRs [#40](https://github.com/LVTD-LLC/citeguild/pull/40) and
  [#41](https://github.com/LVTD-LLC/citeguild/pull/41).
- [x] Public terms, privacy, pricing, support contact, signup policy, and
  backlink language describe actual MVP behavior.
- [ ] CG-034: Scribe/editor completes a genuine search, selects or rejects the
  result, and a normally approved publication/sync proves the intended active
  graph edge. Do not manufacture a link to check this box.
- [ ] Rasul records the final launch decision. Only an explicit **launch**
  decision authorizes an announcement.

## Component diagnosis and recovery

Start with the exact deployed release and the public aggregate health response.
Use approved CapRover API/CLI or SSH access; never use a browser dashboard for
infrastructure changes and never paste an app definition containing secrets.

| Component | Diagnose | Recover or escalate |
| --- | --- | --- |
| Web/API/MCP | Require TLS and `/api/healthcheck` HTTP 200; compare `release` with the intended 40-character SHA; inspect safe request/error logs | Stop rollout on a mismatch. Roll back workers first, then web, to the same known-good SHA. Do not reverse migrations automatically. |
| PostgreSQL | Aggregate health, connection saturation, migration state, disk, and recent database errors | Stop new writes for corruption/recovery. Restore into a fresh volume using `backup-recovery.md`; preserve the suspect volume. |
| Redis and Django Q2 | Aggregate health, worker replica, scheduler presence, queue depth, oldest queued/running crawl age, and count movement | Restore Redis availability before adding workers. Let durable PostgreSQL intent recover; do not scale through an unbounded queue. |
| Crawler | Compare sync totals and terminal counts; group safe error codes; check whether active counts progress over ten minutes | Suspend an abusive or unauthorized project. Preserve evidence. Do not weaken same-host, DNS, redirect, size, or content-type controls. Stale work is recovered by the named five-minute schedule. |
| Embeddings | Failure rate, duration, input tokens, provider status, and Qdrant publication errors | Pause indexing if failures or spend are unbounded. Retry only typed retryable failures; never log provider payloads or article text. |
| Qdrant | Authenticated aggregate collection health, dimensions, payload indexes, memory, and eligible point count | Keep PostgreSQL authoritative. Rebuild into a fresh authenticated collection with `rebuild_qdrant_articles`; do not treat a vector snapshot as billing/crawl truth. |
| Stripe | Product/price active state, webhook enabled state, event delivery, and subscription transition logs | Fix delivery/config before changing customer state manually. Replay signed events idempotently and use Stripe as subscription truth. |
| Backups | Healthchecks status, latest snapshot timestamp/ID, retention, and `restic check` | Treat a missed 25-hour success as an incident. Follow `backup-recovery.md`; never restore over production or write a plaintext host dump. |
| PostHog | Recent canonical event ingestion, safe failure rates, and p50/p95 duration | Fix ingestion/schema drift without adding content, URLs, email, credentials, or Stripe IDs. Product analytics is not a substitute for service health. |

API key rotation immediately revokes the prior key. MCP OAuth clients use the
revocation endpoint. For a suspected credential leak, rotate/revoke first,
identify affected clients from safe metadata, and avoid reproducing the token in
the incident record.

## Abuse and crawler incident flow

1. Acknowledge the report and identify the site by opaque project ID or hostname,
   not by copying crawled content.
2. Suspend the project through the authenticated application service boundary;
   suspension removes it from active crawl/search/link eligibility while
   preserving audit history.
3. Preserve safe request IDs, timestamps, typed error codes, transition history,
   and release identity. Never preserve response bodies or credentials in chat.
4. Check submitted authority, same-host redirects, DNS resolution history,
   response size/type, crawl rate, and outbound effects.
5. Rotate affected credentials and patch the safe-fetch boundary if needed.
6. Reactivate only after the cause and owner authority are verified. Notify
   affected users when required.

## Metrics and review cadence

Greg reviews the production PostHog project each workday during launch week and
weekly afterward. Every query filters `environment = 'prod'`.

- Funnel: subscription activated → site submitted → initial index completed →
  credential created → successful search → received citation.
- Reliability: failed/total indexing, embedding, and search; safe error code;
  p50/p95 duration by event and API/MCP transport.
- Unit cost: crawl page counts per activated account; embedding input tokens by
  model and indexed page; search tokens by transport and successful search;
  current provider rates and CapRover cost are joined outside event data.
- Capacity: active articles, queue depth and age, crawl throughput, PostgreSQL
  connections/disk, Qdrant memory/point count, and backup age.

Production verification on 2026-08-02 found live ingestion for site submission,
initial-index completion, embedding, search, and detected/removed citation
events. Search and embedding attempts observed in that window had only
`succeeded` status. This proves ingestion, not a permanent reliability claim.

## Production-safe failure exercise

The CG-034 dogfood served as the launch tabletop with a real non-destructive
failure:

1. **Signal:** the 465-page Built with Django sync stopped changing after its
   first two concurrent page jobs, while aggregate dependency health remained
   green.
2. **Diagnosis:** the dispatcher published a large broker batch. The per-site
   guard let two jobs run; deferred jobs cleared their markers without ensuring
   a later capacity refill.
3. **Containment:** the approved smaller OSIG and LVTD sites completed, search
   stayed available, and no site or dependency was scaled or security control
   weakened. Two orphaned jobs were requeued through the existing durable-state
   transition.
4. **Correction:** PR #41 caps brokered work at open per-site slots and refills a
   slot after each terminal page outcome. Full PostgreSQL CI, real-service
   acceptance, and ReviewGate General/Adversarial 5/5 passed before release
   `d39dee5050eaa21909f9cec1f44d6d3ca5b1cbe1` deployed.
5. **Exit condition:** the original backlog must show continuous progress and
   finish or reach an explainable terminal partial state before CG-034 closes.

The exercise proved an important launch rule: aggregate health is necessary but
not sufficient; operators also watch business-workflow progress and queue age.

## Explicit launch risks

- The $10 unlimited-sites promise has no measured profitable fair-use boundary
  yet. Review crawl and embedding unit cost weekly and introduce transparent
  safeguards before cost or abuse becomes material.
- PostgreSQL and Qdrant are single persistent services. Backups and rebuilds are
  proven, but there is no high-availability replica design.
- Application error tracking is not enabled in the current release. CapRover
  logs, PostHog's privacy-filtered logs/events, aggregate health, and backup
  alerts cover initial operations; enabling Sentry with an approved DSN is a
  recommended post-launch hardening item.
- Semantic relevance is a candidate rank, not factual validation. Editors must
  inspect every source, and CiteGuild must never promise placement or SEO safety.
- The initial production dogfood corpus is small. Latency and relevance results
  do not establish behavior at customer scale.
