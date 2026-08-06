# CiteGuild — Internal Link Inventory

> Every SEO phase must choose links from this inventory and update it when a new page ships.

## Existing pages (link targets)

### Homepage + core marketing

| Slug | URL | Title / anchor candidate | Used by patterns |
|---|---|---|---|
| `/` | https://citeguild.lvtd.dev/ | Find and cite relevant member articles | All |
| `/pricing` | https://citeguild.lvtd.dev/pricing | CiteGuild pricing — $10/month | Compare, playbooks |
| `/blog/` | https://citeguild.lvtd.dev/blog/ | CiteGuild journal | Playbooks |
| `/privacy-policy` | https://citeguild.lvtd.dev/privacy-policy | Privacy policy | Trust/legal only |
| `/terms-of-service` | https://citeguild.lvtd.dev/terms-of-service | Terms of service | Trust/legal only |

There is no public `/about` page. Do not invent one or link authenticated docs as an indexable marketing surface.

### Features

| Slug | URL | Title / anchor candidate | Used by patterns |
|---|---|---|---|
| `/#article-indexing` | https://citeguild.lvtd.dev/#article-indexing | Sitemap-backed article indexing | Alternatives, use cases, playbooks |
| `/#agent-retrieval` | https://citeguild.lvtd.dev/#agent-retrieval | Relevance-ranked retrieval for writing agents | Alternatives, compare, use cases |
| `/#citation-observation` | https://citeguild.lvtd.dev/#citation-observation | Detected member-to-member citations | Compare, use cases, playbooks |
| `/#membership` | https://citeguild.lvtd.dev/#membership | One $10 monthly membership | Alternatives, compare, use cases |

`/uses` remains publicly accessible for transparency but is `noindex` and excluded from the sitemap because its generic technology-stack intent does not support the product's search strategy.

### Tools (free utilities)

No public tools exist yet.

### Blog posts

| Slug | URL | Title / anchor candidate | Inbound links from |
|---|---|---|---|
| `/blog/haro-alternatives` | https://citeguild.lvtd.dev/blog/haro-alternatives | HARO alternatives guide; current source-request platforms; journalist requests versus agent retrieval | Homepage, pricing, blog index |
| `/for/saas-link-building` | https://citeguild.lvtd.dev/for/saas-link-building | SaaS link building without forced swaps; relevance-first source discovery; source-readiness loop | Homepage, pricing |

## SEO-sprint-generated pages

### `/alternatives/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `linkswarm` | 5 | `/alternatives/linkswarm` | Planned | Homepage, pricing, sibling alternatives |
| `ranking-raccoon` | 6 | `/alternatives/ranking-raccoon` | Planned after Phase 4 validation | Homepage, pricing, sibling alternatives |
| `rankchase` | 7 | `/alternatives/rankchase` | Planned after Phase 4 validation | Homepage, pricing, sibling alternatives |
| `linkrocket` | 8 | `/alternatives/linkrocket` | Planned after Phase 4 validation | Homepage, pricing, sibling alternatives |

### `/for/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `saas-link-building` | 2 | `/for/saas-link-building` | Homepage, pricing | Article indexing, agent retrieval, citation observation, pricing, HARO guide; add `/for/bloggers` when Phase 9 ships |
| `bloggers` | 9 | `/for/bloggers` | Planned | Homepage, pricing, sibling use cases |
| `ai-backlinks` | 10 | `/for/ai-backlinks` | Planned | Homepage, pricing, relevant alternatives |

### `/compare/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `citeguild-vs-linkswarm` | 11 | `/compare/citeguild-vs-linkswarm` | Planned | Both alternative pages, pricing, relevant use case |

### `/playbooks/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `backlink-marketplaces` | 3 | `/playbooks/backlink-marketplaces` | Planned | Homepage, pricing, relevant alternatives and use cases |
| `ethical-link-building` | 12 | `/playbooks/ethical-link-building` | Planned | Homepage, pricing, relevant alternatives and use cases |
| `editorial-link-building` | 13 | `/playbooks/editorial-link-building` | Planned | Homepage, pricing, relevant alternatives and use cases |

## Anchor-text guidance

Vary anchors naturally. Useful families include:

- Homepage: “agent-discovered sources,” “the CiteGuild source network,” “make articles discoverable to writing agents”
- Pricing: “the $10 monthly plan,” “CiteGuild membership,” “pricing for unlimited sites”
- Alternatives: “[Brand] alternatives,” “a relevance-first alternative to [Brand],” “[Brand] versus an editorial source network”
- Use cases: “SaaS link building without link swaps,” “source discovery for bloggers,” “AI-assisted editorial citations”

Never use anchors that promise guaranteed links, rankings, placement, or reciprocity.
