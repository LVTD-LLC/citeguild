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

No public blog posts exist yet; `apps/pages/posts/` contains only `.gitkeep`.

## SEO-sprint-generated pages

### `/alternatives/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `featured` | 1 | `/alternatives/featured` | Planned | Homepage, pricing, sibling alternatives |
| `tavily` | 2 | `/alternatives/tavily` | Planned | Homepage, pricing, sibling alternatives |
| `backlinker-ai` | 3 | `/alternatives/backlinker-ai` | Planned | Homepage, pricing, sibling alternatives |
| `exa` | 4 | `/alternatives/exa` | Planned | Homepage, pricing, sibling alternatives |
| `backlinkgpt` | 5 | `/alternatives/backlinkgpt` | Planned | Homepage, pricing, sibling alternatives |
| `linkswarm` | 6 | `/alternatives/linkswarm` | Planned | Homepage, pricing, sibling alternatives |
| `qwoted` | 7 | `/alternatives/qwoted` | Planned | Homepage, pricing, sibling alternatives |
| `sourcebottle` | 8 | `/alternatives/sourcebottle` | Planned | Homepage, pricing, sibling alternatives |

### `/for/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `saas-link-building` | 9 | `/for/saas-link-building` | Planned | Homepage, pricing, relevant alternatives |
| `bloggers` | 10 | `/for/bloggers` | Planned | Homepage, pricing, sibling use cases |
| `ai-backlinks` | 11 | `/for/ai-backlinks` | Planned | Homepage, pricing, relevant alternatives |

### `/compare/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `citeguild-vs-linkswarm` | 12 | `/compare/citeguild-vs-linkswarm` | Planned | Both alternative pages, pricing, relevant use case |

### `/playbooks/[slug]`

| Slug | Ships in phase | URL | Inbound links from | Outbound links to |
|---|---:|---|---|---|
| `backlink-marketplaces` | 13 | `/playbooks/backlink-marketplaces` | Planned | Homepage, pricing, relevant alternatives and use cases |
| `ethical-link-building` | 14 | `/playbooks/ethical-link-building` | Planned | Homepage, pricing, relevant alternatives and use cases |
| `editorial-link-building` | 15 | `/playbooks/editorial-link-building` | Planned | Homepage, pricing, relevant alternatives and use cases |

## Anchor-text guidance

Vary anchors naturally. Useful families include:

- Homepage: “agent-discovered sources,” “the CiteGuild source network,” “make articles discoverable to writing agents”
- Pricing: “the $10 monthly plan,” “CiteGuild membership,” “pricing for unlimited sites”
- Alternatives: “[Brand] alternatives,” “a relevance-first alternative to [Brand],” “[Brand] versus an editorial source network”
- Use cases: “SaaS link building without link swaps,” “source discovery for bloggers,” “AI-assisted editorial citations”

Never use anchors that promise guaranteed links, rankings, placement, or reciprocity.
