# ADR 0012: Keep observations separate from detected network links

- Status: Accepted
- Date: 2026-08-02

## Decision

Keep every normalized HTTP(S) destination in `OutboundLinkObservation`, but
create a `DetectedNetworkLink` only when that destination host resolves to one
member project. An exact current or historical article URL also attaches the
target article; other URLs on the owned member host remain site-level edges.
The observation remains crawl evidence; the detected link is the derived
private network edge.

An edge is active only while its observation, source article, target article,
source project, and target project are all active. Removal, suspension, and
article inactivity retain the edge and first-detected timestamp but mark it
inactive. Reappearance reactivates the same edge. Canonical changes resolve
through retained `ArticleSourceURL` aliases, so a destination does not lose its
target merely because the target now advertises a new canonical URL.

## Access and language

Detail queries are always rooted in an authenticated profile: links given are
scoped through the owned source project, and links received through the owned
target project. Page and site aggregates use the same owner and active-edge
filters. There is no public full-graph query.

The model and service consistently use “detected” terminology. A crawl proves
that a link was observed; it does not prove that CiteGuild caused or converted
the citation.

## Consequences

- External destinations remain useful crawl history without becoming false
  member edges.
- Observation reconciliation and graph lifecycle can evolve independently.
- The derived graph can be rebuilt from PostgreSQL observations and member URL
  history.
- Account deletion can remove personal/member records without a cross-account
  foreign-key deadlock; target deletion nulls the derived target and leaves no
  active edge.
