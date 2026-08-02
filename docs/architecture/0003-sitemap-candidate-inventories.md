# Sitemap candidate inventories

CG-012 turns one validated project sitemap into a complete desired URL set. The
parser fetches every sitemap through `SafeFetchClient`, keeps redirects and
child sitemaps on the project's normalized host, and supports standard
`urlset`, `sitemapindex`, namespaces, and bounded gzip documents. XML entities
are disabled. Configured byte, raw-entry, recursion-depth, and sitemap-file
limits apply across the full traversal, not independently to each branch.

Page URLs are normalized using the shared HTTP(S) identity rules, restricted to
the project host, deduplicated, and sorted. `lastmod` is retained only when it
is a valid ISO date or datetime and remains an advisory hint. Invalid or
off-host page entries are skipped and counted in sanitized diagnostics;
invalid/off-host child sitemaps fail the parse because silently omitting a
branch would make the desired inventory incomplete.

The parser is side-effect free. After the complete set is available,
`SitemapInventoryService.promote` creates an immutable inventory and its
candidate rows in one database transaction, then switches
`Project.active_sitemap_inventory`. A fetch, parse, limit, or database failure
therefore leaves the previous active inventory untouched. Repeating promotion
for the same durable sync request returns the existing inventory without
duplicating candidates. CG-013 will execute this boundary in workers; CG-015
will reconcile promoted candidates into article lifecycle records.
