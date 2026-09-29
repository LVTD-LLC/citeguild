# CiteGuild Product Contract

This file is the durable product source of truth for humans and coding agents.
The fuller rationale and competitive research live in the [CiteGuild product
memo](https://outline.gregagi.com/doc/citeguild-ai-native-editorial-link-network-ss3kILTcjB).

## Product

CiteGuild is a searchable network of member-published articles that AI content
agents use to discover and cite relevant sources while writing blog posts, SEO
content, and documentation.

Position it as an **AI-native editorial source network** or **the source network
for AI content agents**. Do not lead with backlink exchange, automated
backlinks, guaranteed rankings, or placements. CiteGuild helps agents find
useful sources; it does not buy, require, or guarantee a link.

## Customers and Users

- Members are founders, publishers, content teams, agencies, and
  operators with one or more legitimate sites.
- The primary active user is often a writing agent: Codex or Claude Code via
  MCP, OpenClaw or Hermes via CLI, and other automations via API.
- A customer may submit sites without connecting an agent. Onboarding should
  still make agent connection the obvious next step after the first index.

## Membership Contract

- Membership is free; payment is not required for any product feature.
- New registrations require a valid reusable invitation code/link from an active
  existing member. Each member's code and link are available in Settings.
- Existing accounts retain access without entering an invitation.
- Each active account may add unlimited legitimate sitemap-backed sites, subject
  to anti-abuse, crawl-rate, storage, and security controls.
- New Stripe checkouts are disabled. Legacy subscription/invoice management and
  idempotent webhooks remain available; billing status does not gate access.
- `ALLOW_SIGNUPS=False` remains an operator-wide registration pause.

## Core Loop

1. A person signs up using a member invitation and verifies their email.
2. They submit a sitemap URL; CiteGuild infers the initial site name from the
   normalized host and lets them rename it later. Sitemap support is mandatory
   for MVP.
3. CiteGuild parses the sitemap (and sitemap indexes), fetches each page,
   extracts the main article, canonicalizes it, and records basic metadata.
4. CiteGuild creates one embedding for the whole article and stores the vector
   plus retrieval metadata in self-hosted Qdrant. PostgreSQL retains canonical
   account, site, article, sync, content, and link-graph state.
5. The dashboard shows indexing status and offers a Copy Prompt action to
   connect an agent.
6. MCP, CLI, and API callers search active articles with a topic, question,
   passage, or draft section. Results include enough context for the caller to
   judge usefulness; the caller chooses whether to cite one.
7. Approximately daily reconciliation discovers new URLs, refreshes changed or
   stale pages, and marks disappeared or confirmed unavailable pages inactive
   without deleting history.
8. Crawling observes outbound links. Cross-site member-to-member relationships
   are stored as detected citations with source, target, anchor, first/last
   seen, and active state. External and same-site links do not count as network
   citations.

## Interface Contract

- **MCP:** preferred for Codex and Claude Code; semantic member-article search
  is the minimum useful tool.
- **CLI:** preferred for OpenClaw, Hermes, shell agents, and scripts; support
  readable and JSON output.
- **API:** authenticated semantic search plus account/site operations needed by
  the dashboard and other automations.
- **Dashboard:** invitation settings, site CRUD, sitemap/sync state, page counts,
  recent sync errors, Copy Prompt onboarding, and detected links given/received.

All search surfaces should share one service-level contract. Search only active
pages, rank primarily by vector relevance, allow own-domain exclusion, return
source metadata, and never auto-insert a result.

## MVP Scope

In scope:

- Invitation-only account creation and free membership.
- Unlimited sitemap-backed projects/sites per active account.
- Sitemap and sitemap-index parsing.
- Safe HTML fetch, main-content extraction, metadata, canonicalization, and
  content hashing.
- One whole-article embedding per active page in self-hosted Qdrant.
- Authenticated semantic search through MCP, CLI, and API.
- Daily sitemap reconciliation and inactive soft deletion.
- Outbound-link extraction and detected member-to-member citations.
- Minimal dashboard and Copy Prompt onboarding.
- CapRover deployment of app, workers, PostgreSQL, Redis, and Qdrant.

Explicitly deferred:

- Crawling sites without a sitemap.
- Paragraph-, chunk-, or idea-level embeddings, reranking, and advanced quality
  filters.
- Automatic customer-site editing or publishing.
- Guaranteed placements, reciprocity, credits, exchange balancing, outreach,
  chat, requests, negotiations, or manual editorial queues.
- Public trust profiles or a public network graph.
- Multiple plans, trials, annual billing, per-site pricing, or agency features.

## Success Criteria

Measure active accounts, sites per active account, sitemap indexing success, active
articles, searches per connected account/agent, selected/used results when that
signal exists, detected citations and participating sites, citation retention,
member retention, and crawl/embedding/storage cost per account and page.

The decisive validation question is whether writing agents repeatedly search
CiteGuild and create a growing graph of genuinely relevant citations—not only
whether customers pay to submit a sitemap.

## Product Guardrails

- Optimize for reader usefulness and factual fit, not forced link volume.
- Label observed links as detected citations; never attribute causation without
  an explicit future signal.
- Preserve historical records when content becomes inactive.
- Treat corpus quality, hostile content, weak retrieval, passive supply, and
  unlimited-account economics as first-order risks.
- Any proposal that changes pricing, scope, embedding granularity, data
  retention, attribution language, or interface priority must update this file
  and the product memo decision before implementation.
