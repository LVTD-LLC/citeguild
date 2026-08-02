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

- Paying customers are founders, publishers, content teams, agencies, and
  operators with one or more legitimate sites.
- The primary active user is often a writing agent: Codex or Claude Code via
  MCP, OpenClaw or Hermes via CLI, and other automations via API.
- A customer may submit sites without connecting an agent. Onboarding should
  still make agent connection the obvious next step after the first index.

## Commercial Contract

- One subscription: **$10 per month**, monthly billing only.
- No free plan, free trial, annual plan, premium/agency tier, per-site price, or
  backlink/placement purchase.
- An active subscription is required before a site can be added.
- Each subscribed account can add unlimited projects/sites. Operational
  anti-abuse, crawl-rate, storage, and security controls are allowed, but must
  not silently become paid tiers.
- Customers cancel in Stripe's hosted billing portal. A cancellation scheduled
  for period end keeps access through that paid period. Access ends when Stripe
  reports the subscription canceled, unpaid, or expired; `past_due` receives
  Stripe's normal retry grace period.

## Core Loop

1. A person signs up and starts the $10 monthly subscription.
2. They add a site name and sitemap URL; sitemap support is mandatory for MVP.
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
8. Crawling observes outbound links. Member-to-member relationships are stored
   as detected citations with source, target, anchor, first/last seen, and
   active state.

## Interface Contract

- **MCP:** preferred for Codex and Claude Code; semantic member-article search
  is the minimum useful tool.
- **CLI:** preferred for OpenClaw, Hermes, shell agents, and scripts; support
  readable and JSON output.
- **API:** authenticated semantic search plus account/site operations needed by
  the dashboard and other automations.
- **Dashboard:** subscription state, site CRUD, sitemap/sync state, page counts,
  recent sync errors, Copy Prompt onboarding, and detected links given/received.

All search surfaces should share one service-level contract. Search only active
pages, rank primarily by vector relevance, allow own-domain exclusion, return
source metadata, and never auto-insert a result.

## MVP Scope

In scope:

- Account creation and the single subscription gate.
- Unlimited sitemap-backed projects/sites per subscribed account.
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

Measure paid accounts, sites per paid account, sitemap indexing success, active
articles, searches per connected account/agent, selected/used results when that
signal exists, detected citations and participating sites, citation retention,
subscription retention, and crawl/embedding/storage cost per account and page.

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
