# Site metric history

`ProjectMetricSnapshot` stores one first-observed sample per project and UTC day.
Snapshots are retained for the lifetime of the project; deleting a project cascades
its history. Ownership transfers preserve history with the project.

The existing worker setup command registers an hourly recovery sweep and captures
an initial baseline after migrations. The unique project/date constraint makes
retries and overlapping sweeps idempotent. Missing days are not backfilled.
Every project is sampled, including suspended sites, using dashboard counts.
Links use the same active cross-project network query as the dashboard, excluding
self-links. Indexed pages use the dashboard's persisted active article count.

Domain Rating is the latest cached Ahrefs observation, with its original update
timestamp retained. This does not change provider refresh frequency or initiate
extra paid requests. Unknown ratings remain NULL, not zero.

Site details show six independent server-rendered SVG charts and an accessible
values table. Ranges are allowlisted to 30, 90 (default), or 365 days. Only the
owner can read a site's history. Gaps are not interpolated; a single sample is a
dot, not a fabricated trend. Retained database history is not limited by the UI range.
