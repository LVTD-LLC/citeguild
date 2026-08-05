# CiteGuild SEO Sprint — Roadmap

> **Canonical document.** This is the single source of truth for CiteGuild's multi-phase organic search sprint. Structured research lives privately in Rowset; lightweight locators live in `.seo/config.json`.

## How to use this document

1. Read this document, `.seo/brand.md`, `.seo/link-inventory.md`, and `.seo/config.json`.
2. Find the next pending phase in the tracker.
3. Refresh current competitor facts before commercial alternatives or comparison pages.
4. Execute one deployable phase per branch and PR.
5. Run the phase quality gates, update the link inventory, and mark the tracker row complete in the same PR.
6. Follow the repo ship contract: changelog, CI, ReviewGate/current review bots, merge, and production verification.

## Phase Status Tracker

| # | Phase | Pattern | Status | PR |
|---:|---|---|---|---|
| 0 | Technical foundations and measurement | Setup | completed | [#54](https://github.com/LVTD-LLC/citeguild/pull/54) |
| 1 | Current HARO alternatives editorial guide | Editorial | in_progress | `scribe/cg-039-haro-alternatives` |
| 2 | Tavily alternative for editorial source retrieval | Alternatives | pending | — |
| 3 | Backlinker AI alternative | Alternatives | pending | — |
| 4 | Exa alternative for opted-in editorial sources | Alternatives | pending | — |
| 5 | BacklinkGPT alternative | Alternatives | pending | — |
| 6 | LinkSwarm alternative | Alternatives | pending | — |
| 7 | Qwoted alternative | Alternatives | pending | — |
| 8 | SourceBottle alternative | Alternatives | pending | — |
| 9 | CiteGuild for SaaS link building | Use case | pending | — |
| 10 | CiteGuild for bloggers | Audience | pending | — |
| 11 | CiteGuild for AI-assisted backlinks | Use case | pending | — |
| 12 | CiteGuild vs LinkSwarm | Comparison | pending | — |
| 13 | Backlink marketplaces: risks and alternatives | Playbook | pending | — |
| 14 | Ethical link building playbook | Playbook | pending | — |
| 15 | Editorial link building playbook | Playbook | pending | — |
| 16 | Internal-link spine audit | Internal links | pending | — |
| 17 | Listicle outreach | Off-page | pending | — |
| 18 | Directory submissions | Off-page | pending | — |

**Conventions:** `pending` → `in_progress` → `completed`. Add the branch while work is active and the PR number after merge. A skipped phase needs a one-line reason.

## Reference Data

### Site facts

- **Production domain:** `https://citeguild.lvtd.dev`
- **Future domain:** `citeguild.app` — DNS did not resolve on 2026-08-05; do not treat it as canonical until migration is deliberate and verified.
- **Keyword data source:** DataForSEO, United States / English, measured 2026-08-05.
- **Owned search source:** GSC property `sc-domain:lvtd.dev`, filtered to pages containing `citeguild.lvtd.dev`.
- **Authority baseline:** DataForSEO returned zero backlink-summary rows and zero ranked keywords. Treat effective authority as near-zero and target KD ≤10 initially.
- **Owned search baseline:** GSC returned 0 query/page rows, 0 clicks, and 0 impressions for the prior 90 days.
- **Product analytics:** PostHog project `538803` is the sole SEO conversion source. Early product usage exists, but no identifiable organic search attribution in the prior 90 days.
- **Stack:** Django 6 templates, controller-based routing, Tailwind CSS.
- **Brand:** primary green `#15803D`, slate `#0F172A`, system sans-serif.
- **Marketing root:** `apps/pages/`, `frontend/templates/pages/`, and `frontend/templates/base_landing.html`.

### Tool evidence snapshot

| Source | Status | Credential/config evidence | API/tool evidence | Used for | Config saved | Reason |
|---|---|---|---|---|---|---|
| GSC | connected | Infisical service account; access to `sc-domain:lvtd.dev` | Sites, Search Analytics, and sitemaps APIs returned 200; CiteGuild sitemap submitted 2026-08-05 | Owned queries, striking distance, sitemap state | `gsc_property`, page filter, sitemap record | Submission is pending processing with 0 errors and 0 warnings; zero owned-search rows remain a connected sparse result. |
| Ahrefs | missing | Checked loaded tools, env, operator workspace routing notes (external to this repo), repo config, and Infisical `/services/ahrefs` | No usable tool or credential found | DR, keyword gaps, backlinks | None | DataForSEO supplies measured market data instead. |
| DataForSEO | connected | Toolkit plus Infisical `/services/dataforseo` | Backlinks, ranked keywords, ideas, overviews, and SERP calls succeeded | Volume, KD, CPC, intent, SERP, baseline | Location/language | Domain rows are sparse; candidate metrics are measured. |
| Plausible | attempted_failed | API key and custom host documented | V2 queries for both candidate site IDs returned 401 | Organic pages/goals | None | Credential exists, but CiteGuild site access/config is unavailable. |
| PostHog | connected | Personal API key; project discovered through management API | Event and pageview HogQL queries succeeded | Conversion/event weighting | Project ID | Early events exist; no organic attribution yet. |
| Exa | connected | Runtime key and workspace routing | Competitor and listicle discovery succeeded | Discovery | Provider | Found direct and adjacent competitors plus outreach targets. |
| Firecrawl/Jina/WebFetch | connected | Firecrawl and Jina runtime keys | Firecrawl extracted LinkSwarm, Backlinker AI, Featured, and Tavily; two follow-ups were rate-limited | Current positioning/pricing/features | Provider | Core extraction succeeded; rate limits are recorded. |

Private evidence dataset: [CiteGuild SEO Tool Evidence](https://rowset.lvtd.dev/datasets/45770624-6e51-4a64-be94-6dec3d514c0d).

### Existing programmatic surface

| Surface | State | Do not duplicate |
|---|---|---|
| Homepage | Public, indexable | Product promise and membership model |
| Pricing | Public, indexable | $10 monthly, unlimited sites, no trial/free tier |
| Journal | Public index, no posts yet | Blog index and schema infrastructure |
| Authenticated docs | `noindex`, login required | MCP/CLI/API product documentation is not a public SEO surface |
| `/uses` | Public transparency page, `noindex` and excluded from sitemap | Do not target generic technology-stack intent or link from SEO page families |

### Critical files

| File | What lives there |
|---|---|
| `apps/pages/urls.py` | Public marketing routes |
| `apps/pages/views.py` | Marketing and blog views |
| `frontend/templates/base_landing.html` | Public shell, global metadata defaults, navigation |
| `frontend/templates/pages/landing-page.html` | Homepage copy and current `WebSite` schema |
| `frontend/templates/pages/pricing.html` | Pricing metadata and conversion page |
| `citeguild/sitemaps.py` | Static and blog sitemap generation |
| `frontend/templates/robots.txt` | Crawl rules and sitemap reference |
| `apps/pages/services.py` | Blog metadata and JSON-LD helpers |
| `apps/pages/posts/` | Repository-backed public posts; currently empty |
| `apps/core/analytics.py` and `ANALYTICS.md` | Canonical product events and privacy contract |

## Keyword Research Appendix

Private opportunity dataset: [CiteGuild SEO Opportunities](https://rowset.lvtd.dev/datasets/0d4c2270-cc89-45ce-b15a-b30789cede3b). Metrics below are US/English DataForSEO measurements from 2026-08-05 unless marked derived.

### Owned search and analytics baseline

- GSC: 0 rows, 0 clicks, 0 impressions in the prior 90 days for `citeguild.lvtd.dev`.
- DataForSEO: 0 ranked keywords and 0 backlink-summary result rows for `citeguild.lvtd.dev`.
- PostHog: 20 pageviews across 4 users in 90 days. Product truth events include one checkout start and one subscription activation, but no organic referrer signal.
- Plausible: unavailable for CiteGuild due an invalid key/site pairing.
- There are no striking-distance queries yet.

### Alternatives candidates

| Phase | Target | Measured demand | KD | CPC | Confidence | Positioning constraint |
|---:|---|---:|---:|---:|---|---|
| 1 | `/blog/haro-alternatives` | `haro alternatives` 90 | 0 | $36.15 | measured | Plural listicle intent; compare active request services and distinguish persistent agent retrieval. |
| 2 | `/alternatives/tavily` | `tavily alternatives` 70 | 0 | $14.27 | measured | Tavily searches the broad web; CiteGuild searches opted-in editorial sources. |
| 3 | `/alternatives/backlinker-ai` | Competitor brand 50 | 2 | $16.02 | derived modifier | CiteGuild does not automate outreach or guarantee 3+ links. |
| 4 | `/alternatives/exa` | `exa alternatives` 30 | — | $7.81 | measured | Exa is broad neural search; CiteGuild is a focused member corpus. |
| 5 | `/alternatives/backlinkgpt` | Competitor brand 20 | 0 | $7.09 | derived modifier | CiteGuild does not prospect or send email campaigns. |
| 6 | `/alternatives/linkswarm` | No measured row | — | — | derived | Closest strategic competitor; contrast retrieval with circular exchanges and credits. |
| 7 | `/alternatives/qwoted` | `qwoted alternatives` 10 | — | $25.05 | measured | PR/source requests versus persistent agent retrieval. |
| 8 | `/alternatives/sourcebottle` | `sourcebottle alternatives` 10 | — | — | measured | Source requests versus a sitemap-backed article index. |

### Product-memo competitor watchlist

Rasul supplied the product memo's 2026-07-31 competitive scan during Phase 0. Keep these candidates in research, but do not displace the measured tracker until current positioning and DataForSEO demand are re-verified.

| Candidate | Category distinction | Promotion gate |
|---|---|---|
| Ranking Raccoon | Moderated human SEO community with site browsing, messaging, and placement verification | Verify current pricing and demand for `ranking raccoon alternatives`. |
| RankChase | Niche/domain-metric matching plus human link-exchange requests | Verify current pricing and demand for `rankchase alternatives`. |
| LinkRocket | Credit-based backlink exchange | Verify product status, indexed pages, and brand/modifier demand. |
| RobotSpeed | Automated contextual placements and DR-growth promise | Verify live behavior, policy fit, and demand before considering an alternative page. |
| LinkDR | AI-assisted prospecting, outreach, and managed placements | Verify pricing, current positioning, and whether search intent overlaps CiteGuild's source-discovery wedge. |

The memo also strengthens four non-keyword inputs: use “AI-native editorial source network” as the category phrase; treat MCP, CLI, and API as first-class high-intent surfaces; address founders/publishers, content teams, agencies, and agent builders explicitly; and explain the relevance-first, non-guaranteed editorial guardrail wherever backlink-adjacent intent appears.

### Use-case and audience candidates

| Phase | Target | Keyword | Volume | KD | CPC | Intent |
|---:|---|---|---:|---:|---:|---|
| 9 | `/for/saas-link-building` | `saas link building` | 260 | 0 | — | commercial |
| 10 | `/for/bloggers` | `blogger backlinks` | 90 | 0 | — | informational |
| 11 | `/for/ai-backlinks` | `ai backlinks` | 50 | 8 | $29.82 | commercial |

### Comparison candidates

| Phase | Target | Volume | Confidence | Notes |
|---:|---|---:|---|---|
| 12 | `/compare/citeguild-vs-linkswarm` | 0 | derived | Strategic differentiation after both supporting alternative pages exist. |

Third-party `exa vs tavily` has measured demand of 90, KD 0, but is out of scope because a CiteGuild page should not exist solely to compare two other products.

### Playbook candidates

| Phase | Target | Keyword | Volume | KD | CPC | Intent |
|---:|---|---|---:|---:|---:|---|
| 13 | `/playbooks/backlink-marketplaces` | `backlink marketplace` | 110 | 0 | $40.41 | commercial |
| 14 | `/playbooks/ethical-link-building` | `ethical link building` | 40 | 0 | — | informational |
| 15 | `/playbooks/editorial-link-building` | `editorial link building` | 20 | 3 | $51.39 | navigational |

### Conversion weighting

| Candidate | Signal | Priority impact |
|---|---|---|
| SaaS link building | Volume 260, KD 0, strong product fit | High despite no organic conversion history. |
| Backlink marketplaces | CPC $40.41, volume 110, KD 0 | High commercial value; keep the page educational and honest. |
| Editorial link building | CPC $51.39, KD 3 | Raise above raw volume would suggest. |
| AI backlinks | CPC $29.82, KD 8 | Viable after the domain has a small internal-link spine. |
| MCP/developer alternatives | Existing MCP initialization/tool-call activity | Supports Tavily and Exa alternative pages, but attribution is not yet organic. |

### Saturated or misleading terms to avoid initially

| Keyword | Volume | KD | Reason |
|---|---:|---:|---|
| `backlinks` | 5,400 | 70 | Far above the site's authority. |
| `link building` | 2,400 | 73 | Head term is unwinnable at current authority. |
| `ai citation tool` | 70 | 63 | Usually implies AI visibility tracking, which CiteGuild does not provide. |
| `ai visibility tool` | 1,600 | 25 | Wrong primary category and too competitive for day zero. |
| `source finder` | 1,000 | 12 | Ambiguous intent; revisit after authority and public source-search proof grow. |

### Out of scope

- Guaranteed-backlink, paid-placement, reciprocal-link, PBN, and “undetectable exchange” intent.
- AI citation monitoring/brand visibility claims that CiteGuild does not provide.
- General web search/extraction intent unrelated to the opted-in member corpus.
- Public SEO pages for authenticated documentation until a deliberate public-docs decision is made.

## Phases

### Phase 0 — Technical foundations and measurement

**Why:** the live deterministic audit passes basic sitemap and robots checks, but the structured-data and measurement foundation is not ready for a programmatic page family.

**Scope:**

1. Add reusable JSON-LD helpers for `SoftwareApplication`, `Organization`, `FAQPage`, `BreadcrumbList`, and `Article`.
2. Replace the homepage-only `WebSite` schema with valid `SoftwareApplication` plus `Organization` data.
3. Decide whether `/uses` should be repurposed as a product-use page or removed from the public sitemap; its current generic technology-stack intent is weak.
4. Add meaningful static-page `lastmod` handling or document why static entries intentionally omit it.
5. Submit `https://citeguild.lvtd.dev/sitemap.xml` to GSC property `sc-domain:lvtd.dev` and verify acceptance.
6. Fix Plausible site provisioning/access or formally choose PostHog as the sole SEO conversion source.
7. Define public internal-link destinations or section anchors for product features before Phase 1, because pattern pages need more than homepage/pricing links.

**Phase 0 decisions and evidence:**

- `/uses` remains available as a transparency page but is `noindex` and removed from the sitemap; generic technology-stack intent is not a product acquisition target.
- Static marketing URLs intentionally omit `lastmod`. CiteGuild will not publish deployment dates as fake content-change dates; accurate modification dates remain attached to repository-backed articles.
- PostHog project `538803` is the sole SEO conversion source. Its consented pageviews, sanitized first/latest-touch attribution, CTA events, signup, and Stripe-confirmed activation contract cover organic landing analysis; Plausible remains an unavailable optional source rather than a launch dependency.
- The homepage exposes stable feature anchors for article indexing, agent retrieval, citation observation, and membership. Future page families should link to those anchors until dedicated public feature pages earn their own search intent.
- `https://citeguild.lvtd.dev/sitemap.xml` was submitted to `sc-domain:lvtd.dev` on 2026-08-05 at 16:40:58 UTC. Search Console reported pending processing, 0 errors, and 0 warnings immediately after submission.
- The production deterministic audit returned no findings before implementation. Re-run it after deployment and validate the new homepage schema separately.

**Verification:** production sitemap and robots return 200; no duplicate titles/descriptions; every indexable page has one H1 and a self-canonical; homepage schema validates; GSC records the sitemap; organic landing attribution is measurable or explicitly assigned to PostHog.

### Phase 1 — HARO alternatives editorial guide

Publish `/blog/haro-alternatives` as a current, balanced listicle because the measured query has plural comparison intent. Verify the HARO/Featured/Connectively relationship and every named service against current official sources. Compare options with consistent criteria, explain when request platforms win, and position CiteGuild as a different persistent source-discovery workflow rather than a direct journalist-request replacement. Emit `BlogPosting`, `ItemList`, `BreadcrumbList`, and `FAQPage`, add at least three in-body internal links and two inbound links, and keep the article above 1,500 words.

The previously planned `/alternatives/featured` route is retired from this sprint to prevent intent mismatch and cannibalization.

### Phases 2–8 — Alternatives family

Build the seven remaining pages in tracker order. Every page must contain at least 600 words, `SoftwareApplication`, `BreadcrumbList`, `FAQPage`, at least three honest tradeoffs where the competitor wins, and the required sibling/feature/tool links. If Phase 0 does not create enough public feature/tool destinations, do not fake the link minimum—build the spine first and update the tracker.

Refresh pricing and features from each competitor's official site immediately before writing. Target the keyword and constraints in the Alternatives table above.

### Phases 9–11 — Use-case and audience family

Each page needs at least 800 words, `SoftwareApplication`, `BreadcrumbList`, `FAQPage`, two feature links, two useful public resource/tool links, and one sibling `/for/` link. Lead with relevance and source usefulness rather than backlink guarantees.

### Phase 12 — CiteGuild vs LinkSwarm

Ship only after both products' current behavior has been re-verified and `/alternatives/linkswarm` exists. Use at least 700 words, `BreadcrumbList`, `FAQPage`, both relevant alternative pages, a `/for/` page, and pricing. Compare facts, not motives; explain CiteGuild's rejection of credits, circular exchanges, and automatic placement.

### Phases 13–15 — Playbooks family

Each playbook needs at least 2,500 words, `Article` and `BreadcrumbList` schema, primary-source support, practical steps, and the full internal-link minimum. Keep claims sourceable. The backlink-marketplace page should explain categories, disclosure, risk, and relevance-first alternatives rather than becoming a marketplace directory.

### Phase 16 — Internal-link spine audit

Verify that every generated page has at least two inbound links, no page is orphaned, anchors vary naturally, and the homepage/pricing/journal navigation exposes the right hubs without overwhelming the public shell.

### Phases 17–18 — Off-page execution

The private [CiteGuild SEO Backlink Targets](https://rowset.lvtd.dev/datasets/cd58d6fe-4e69-463b-8ce4-93a84393c314) dataset contains qualified listicles and directory candidates. Re-verify editorial policy before outreach. Reject undisclosed paid placement, circular exchanges, fake reviews, and guaranteed links. Track status in Rowset, not git.

## Current handoff

Initialization and Phase 0 are complete in [PR #54](https://github.com/LVTD-LLC/citeguild/pull/54). Phase 1 is in progress on `scribe/cg-039-haro-alternatives` as an editorial guide matching the plural listicle SERP; `/alternatives/featured` has been retired. The product-memo competitor watchlist still requires live demand and product re-verification before promotion.
