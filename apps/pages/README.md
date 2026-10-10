# Blog Posts

Published blog posts live in `apps/pages/posts` as Markdown files. Every `*.md`
file in that directory is public on deploy at `/blog/{filename-slug}`.

Required frontmatter:

```yaml
---
title: Agent-managed workflows
description: A concise search snippet for the article.
published_at: 2026-07-04
---
```

Optional frontmatter:

```yaml
updated_at: 2026-07-04
author: Jane Doe
keywords:
  - Django
  - SaaS
topics:
  - product updates
canonical_url: https://example.com/blog/agent-managed-workflows
image: /static/blog/agent-managed-workflows.png
image_alt: Dashboard showing an agent-managed workflow
robots: index, follow
howto_steps:
  - name: Define the task
    text: Write the specific outcome before choosing an approach.
  - name: Verify the result
    text: Check the completed work against the outcome.
```

Use `howto_steps` only for an actual instructional article. Each entry requires
nonblank `name` and `text` strings and must accurately summarize a visible step
in the article, in the same order. This adds optional `HowTo` structured data
alongside `BlogPosting` and breadcrumbs; omitted or empty steps add none.
Structured data does not guarantee a search feature or rich result.

Use lowercase filename slugs such as `agent-managed-workflows.md`. There is no
draft status or database sync path; keep unfinished posts outside this folder.
