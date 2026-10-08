# IndexNow

CiteGuild notifies https://api.indexnow.org/indexnow after successful Deploy Prod runs and hourly at minute 17 UTC (GitHub scheduling can be delayed). Only canonical URLs from https://citeguild.dev/sitemap.xml are submitted: marketing and public blog pages, never member article URLs, account pages, or authenticated docs.

The public `/indexnow-key.txt` ownership proof uses a site-specific random value, not an application credential. It reports the running image's CITEGUILD_RELEASE. No new environment variables, migrations, or provider credentials are needed.

The workflow verifies the deployed revision before submitting. Deployment notifications refresh all public URLs, covering static/template changes without lastmod. Hourly checks compare full sitemap timestamps and revision fingerprints, include previously observed removals, and retry failed deployment refreshes. Failed or partial submissions never advance the checkpoint. HTTP 200 means received; 202 means received with key validation pending. Neither proves indexing.

## Operations

- Run the `IndexNow public URL changes` workflow manually to retry.
- Read-only check: `python citeguild/indexnow.py --site-url https://citeguild.dev --dry-run`.
- Explicit full refresh: `uv run python manage.py submit_indexnow`.
- Removed URLs can be supplied via a JSON array using `--previous FILE`.

State is stored in a serialized GitHub Actions cache. Cache eviction resets the baseline and loses historical removal evidence; URLs added and deleted between checks are not observed. Repository-backed content changes require deployment. No Google indexing guarantee is implied.

The historical MVP taskboard is archived; this owner-requested follow-up is tracked by the PR and changelog without reopening that board.
