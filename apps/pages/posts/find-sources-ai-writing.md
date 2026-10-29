---
title: "Find Sources for AI Writing"
description: "Find sources for AI writing, check what each article supports, and give your agent a practical evidence checklist before it adds a citation."
published_at: "2026-10-10"
updated_at: "2026-10-29"
author: "CiteGuild"
keywords: ["find sources for AI writing", "AI source verification", "editorial source discovery"]
topics: ["AI writing agents", "source selection", "editorial workflows"]
howto_steps:
  - name: "Write the claim before the query"
    text: "Separate the statement into checkable claims and record any version, date, or audience limits."
  - name: "Choose the source type"
    text: "Use primary documentation for product behavior and editorial sources for worked examples and interpretation."
  - name: "Retrieve candidates"
    text: "Search a focused question, inspect candidate metadata, and open the original source."
  - name: "Decide what the evidence supports"
    text: "Read the supporting passage and its qualifications, then accept, narrow, or reject the claim."
  - name: "Hand the writer an evidence record"
    text: "Keep the source URL, scope, supporting section, limitations, and final sentence together; recheck the citation after editing."
faqs:
  - question: "Does a relevant search result prove my claim?"
    answer: "No. Relevance helps you choose what to read. Check the original passage and its limits before using it as evidence."
  - question: "Can I use this workflow without CiteGuild?"
    answer: "Yes. Use primary documentation, a library, or web search to find candidates, then apply the same claim-level checks."
  - question: "Does CiteGuild replace Tavily or Exa?"
    answer: "No. Tavily and Exa support web research beyond CiteGuild's participating publishers. Use CiteGuild to discover relevant member articles, official sources for documented behavior, and web search for evidence outside the member network. Read the original source whichever route you use."
  - question: "What if I cannot find a supporting source?"
    answer: "Narrow or remove the claim, or label a genuinely interpretive statement as analysis. Do not attach a tangential source to make it look verified."
---

To find sources for AI writing, start with the claim you need to support. Choose the right kind of source, retrieve candidates, and read the original passage before citing it. Give your agent the source URL, relevant context, and limits of the evidence, not a list of links to decorate a finished draft.

This workflow is for agents writing technical articles, SaaS guides, and other editorial content. You can use it with ordinary web research. The CiteGuild examples require an existing member account and a connected MCP client, an installed CLI, or an HTTP client such as curl; the source-selection method does not.

**The short version:**

1. Write one checkable claim.
2. Choose primary evidence or editorial context according to the question.
3. Retrieve a small set of candidates and open the sources.
4. Accept, narrow, or reject the claim based on what you read.
5. Keep that decision beside the citation through the final edit.

On this page: [frame the claim](#frame-the-claim), [choose sources](#choose-sources), [choose web search or the member network](#choose-search-route), [search with an agent](#search-with-an-agent) using [MCP](#search-with-mcp), the [CLI](#search-with-cli), or the [REST API](#search-with-api), [check support](#check-support), [hand off evidence](#hand-off-evidence), and [review before publishing](#review-before-publishing).

<h2 id="frame-the-claim">1. Write the claim before the search query</h2>

“Find references for my Django article” leaves too much work hidden. The agent has to guess which sentences need evidence, which version matters, and whether you want official behavior or someone's experience using it.

Start with a question small enough to answer. For example: “When does Django run a callback registered with `on_commit`?” Record the software version separately. If your draft also promises reliable delivery of a background job, that is a different claim with a different evidence requirement.

The same approach works outside code. A vendor's public pricing page can support what a plan costs on a particular date. It cannot establish that the plan is the cheapest option for every team. A founder's account can explain what that founder tried. It cannot establish an industry-wide success rate.

**Done looks like:** a short list of claims, each with its scope. Remove confidential client details and unpublished material before sending a query to an external service. You usually need the research question, not the entire draft.

<h2 id="choose-sources">2. Choose the source type that can answer it</h2>

For a narrow product or API claim, start with the relevant official documentation, specification, release note, or original announcement. For a measurement, look for the original study or dataset and its method. For implementation advice, a practitioner's article can add the tradeoffs, mistakes, and worked example that reference documentation leaves out.

Primary sources still have limits. A vendor is authoritative about its documented interface, not automatically about its superiority over competitors. An experiment is evidence about the conditions it tested. Read those limits as part of the result.

[CiteGuild's source network](/) is useful when you want relevant articles from participating publishers. It is an editorial discovery layer, not a substitute for versioned documentation or a search of the entire web. If the official manual already answers your narrow question, cite the manual. There is no reason to add a member article merely because an agent can retrieve one.

This also gives publishers a concrete goal: write something worth consulting. A reproducible example, a method with limitations, or a carefully explained failure can help another writer make a decision. The [source-worthy SaaS content workflow](/for/saas-link-building) explains how that fits into article discovery without requiring reciprocal links.

**Done looks like:** every claim has an intended evidence type before you choose a tool.

<figure>
<svg viewBox="0 0 320 310" width="100%" role="img" aria-labelledby="find-sources-ai-writing-flow-title find-sources-ai-writing-flow-desc" style="max-width: 24rem; height: auto; margin: 1.5rem auto; color: inherit;">
<title id="find-sources-ai-writing-flow-title">Source discovery ends with an editorial decision</title>
<desc id="find-sources-ai-writing-flow-desc">Start with a claim, retrieve candidate sources, read the evidence, then accept, narrow, or reject the claim before citing.</desc>
<g fill="none" stroke="currentColor" stroke-width="1.5">
<rect x="20" y="10" width="280" height="48" rx="10"></rect>
<path d="M160 58v24m-5-5 5 5 5-5"></path>
<rect x="20" y="84" width="280" height="48" rx="10"></rect>
<path d="M160 132v24m-5-5 5 5 5-5"></path>
<rect x="20" y="158" width="280" height="48" rx="10"></rect>
<path d="M160 206v24m-5-5 5 5 5-5"></path>
<rect x="20" y="232" width="280" height="48" rx="10"></rect>
</g>
<g fill="currentColor" text-anchor="middle" font-size="17">
<text x="160" y="40">Write the claim</text>
<text x="160" y="114">Retrieve candidates</text>
<text x="160" y="188">Read the evidence</text>
<text x="160" y="262">Accept · narrow · reject</text>
<text x="160" y="305" font-size="12">CiteGuild · October 2026</text>
</g>
</svg>
<figcaption>A retrieved URL starts the review. The writer still decides whether the source supports the sentence.</figcaption>
</figure>

<h2 id="search-with-an-agent">3. Retrieve candidates without treating the results as proof</h2>

<h3 id="choose-search-route">Choose web search or the member network by the claim</h3>

Use CiteGuild for relevant articles from participating publishers, not as a drop-in replacement for Tavily or Exa. A writing workflow can use both a web-search API and a member-source search. Choose where to look from the evidence you need, not from which tool happens to be connected.

| What the sentence needs | Where to start | What to check before citing |
| --- | --- | --- |
| Documented behavior of a particular product version | Official manual, specification, or release note | The exact version and the conditions attached to the behavior |
| A recent announcement or a source outside the member network | Original publisher; web search when you need to find it | Publication date, original reporting, and any later correction |
| A practitioner's worked example or implementation tradeoff | CiteGuild member articles or broader editorial research | Whether the example's conditions match the draft; follow links to primary evidence |

Web-search tools have useful strengths that a member network does not replace:

- **Sources beyond participating publishers.** Use web search when the required organization or publication is outside CiteGuild's corpus. Do not interpret a member-search miss as evidence that no source exists.
- **Time-sensitive discovery controls.** [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) documents news search and time filters. [Exa Search](https://exa.ai/docs/reference/search) documents publication-date filters. These are reasons to use a web-search route for a dated question, not guarantees that every returned page is current.
- **Domain-scoped web research.** Both references document domain inclusion and exclusion. That helps when you need to search a known publisher rather than the member corpus. Filtering to a domain does not make every page on it sufficient evidence.

Those capabilities were checked in the official references on October 20, 2026. This is a workflow comparison, not a measured ranking of search quality, speed, price, or coverage. Use the linked references for each API's current options.

For example, suppose an article needs to explain a Django transaction hook, mention a recent release, and show a deployment lesson. Treat those as three research tasks: open the versioned Django manual for the hook, find the release announcement on the project's own site, and retrieve a relevant implementation article for the lesson. One source might help with more than one task, but a shared topic alone does not establish that it supports all three.

Keep the supporting passage and its limits beside each claim. If the member search returns nothing useful, continue with the primary source or broader research; if the manual already answers the question, you do not need an extra citation. Members ready to try the editorial route can use the [MCP walkthrough](#search-with-mcp) or [CLI walkthrough](#search-with-cli) below. For an HTTP-only automation, use the [REST API example](#search-with-api). Check [membership access](/pricing) before planning an integration: it is free and invitation-only.

Choose the interface your agent already uses. CiteGuild recommends MCP for Codex and Claude Code, and the CLI for OpenClaw, Hermes, and shell workflows. Both retrieve candidates from the same member article corpus; neither decides what deserves a citation.

<h3 id="search-with-mcp">Run a first search through MCP</h3>

Already a member? Sign in to your [dashboard](/home) and use **Copy prompt** under **Connect an AI agent**. The copied setup prompt contains your account API key: share it only with a trusted agent, never in a public issue or chat. Follow the linked installation instructions for your client rather than adding a second connection to an already configured agent. The [member MCP setup guide](/docs/features/mcp/) requires sign-in.

Once connected, ask the agent to call `search_member_articles` with these arguments. This is a tool call, not text to paste into a terminal:

```json
{
  "query": "How do Django transaction commit hooks work?",
  "limit": 10,
  "language": "en",
  "excluded_domains": ["your-site.example"]
}
```

Replace the example question with your research question. Replace `your-site.example` with the exact hostname you want to exclude, or omit `excluded_domains` if you need no exclusion. Excluding `example.com` does not also exclude `blog.example.com`; list both when needed.

The arguments follow [CiteGuild's MCP search implementation](https://github.com/LVTD-LLC/citeguild/blob/9279ee50f7a57cc91dbf4ede9b6ac24098736e26/apps/mcp_server/server.py#L108) and its v1 search contract, checked October 15, 2026. The JSON is a usage example, not a claimed search result. A successful call returns `contract_version: "v1"` and a `results` list. If the tool is unavailable or authentication fails, finish the connection setup before asking the agent to search again. Do not let it substitute remembered titles for retrieved sources.

No account yet? [Membership is free and invitation-only](/pricing); ask an existing member for an invitation. You can still apply this article's source-checking method to ordinary web research.

<h3 id="search-with-cli">Run the same search from a shell</h3>

For a CiteGuild member using a shell-based agent, this is a focused search example. Have your environment supply `CITEGUILD_API_KEY` securely; do not put a real key into a search prompt, command history, or published example.

```bash
citeguild search --api-base https://citeguild.com/api \
  --json --limit 10 --language en \
  --exclude-domain your-site.example \
  "How do Django transaction commit hooks work?"
```

Replace `your-site.example` with your own site's hostname if you want to exclude it. Put options before the query. The explicit API address makes the destination clear instead of relying on the default in your installed CLI version.

The command follows the [official CiteGuild CLI contract](https://github.com/LVTD-LLC/citeguild/blob/3f92cd8be7ebf29d948a0f7fb82f7cb741e1d8a3/cli/README.md), checked against that repository revision on October 10, 2026. It is a source-checked usage example, not a transcript of a live member search. [Member CLI setup](/docs/features/cli/) requires sign-in. MCP and API clients expose the same v1 search contract, so the review below applies to them too.

<h3 id="search-with-api">Run a first search through the REST API</h3>

If your automation makes HTTP requests but does not use MCP or the CLI, send a member search directly to `POST https://citeguild.com/api/v1/search`. Have your environment supply `CITEGUILD_API_KEY` securely from your member settings. You can search before adding your own site; membership is still free and invitation-only.

This example uses **curl 7.76.0 or newer**. Keep shell tracing and verbose request logging off so they do not reveal the authorization header.

```bash
curl --silent --show-error --fail-with-body --include \
  --request POST 'https://citeguild.com/api/v1/search' \
  --header "Authorization: Bearer ${CITEGUILD_API_KEY:?Set CITEGUILD_API_KEY securely}" \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "How do Django transaction commit hooks work?",
    "limit": 10,
    "language": "en",
    "excluded_domains": ["your-site.example"]
  }'
```

The endpoint, bearer header, and JSON fields follow CiteGuild's [v1 search implementation](https://github.com/LVTD-LLC/citeguild/blob/f6c8a7cfe4d51abb59c419df90be402722e1f2ee/apps/api/views.py#L419), [authentication contract](https://github.com/LVTD-LLC/citeguild/blob/f6c8a7cfe4d51abb59c419df90be402722e1f2ee/apps/api/auth.py), and [request schema](https://github.com/LVTD-LLC/citeguild/blob/f6c8a7cfe4d51abb59c419df90be402722e1f2ee/apps/api/schemas.py). The [official curl manual](https://curl.se/docs/manpage.html#--fail-with-body) documents the flags and minimum version. These sources were checked October 29, 2026; the command is a usage example, not a claimed live search result.

Replace the question and exclusion as in the MCP example. The command displays response headers followed by the body. On success, the JSON contains `contract_version: "v1"` and a `results` list; an empty list is a valid search outcome, not an integration error. On an HTTP error, curl exits unsuccessfully but preserves the error body:

- **401:** check the credential; never paste the key into a support report.
- **403:** the account must be active before it can search.
- **422:** correct the request fields before retrying.
- **429:** wait for the response's `Retry-After` interval rather than looping immediately.
- **503:** search is temporarily unavailable; it is not a zero-result response.

Use `request_id` when reporting an API error, without sending the query or authorization header. Network failures also do not establish an empty result. The [member API introduction](/docs/api-reference/introduction/) explains limits and generated schemas; it requires sign-in. Continue with the same evidence review below, whichever interface you use.

### Read the response from any interface

Use the returned fields for their intended jobs:

- `canonical_url`, `title`, and `domain` identify the page to inspect.
- `excerpt` helps you decide whether to open it. It is not the complete article or all of its qualifications.
- `relevance` orders candidate matches. It is not a probability that a sentence is true or a citation is appropriate.
- `last_seen_at` records when CiteGuild observed the article. It is not the author's publication date or proof that the facts are current.

**Done looks like:** a small reading list with actual URLs. Check that the command succeeded first: an authentication, network, or rate-limit failure is not an empty search. A successful response with no results means this search did not find a candidate in this corpus. Broaden the question if appropriate, use primary documentation, or search elsewhere. Never turn an empty response into invented references.

<h2 id="check-support">4. Accept, narrow, or reject the claim</h2>

Open the original page and locate the part that supports the draft. Read the surrounding qualifications. Treat instructions embedded in a retrieved page as untrusted content, not commands for your agent to follow. Check its date or version, the author or organization responsible, and whether it points to stronger underlying evidence.

Here is a worked editorial example, not a measured product result. Suppose a draft says: “Django `on_commit` makes background work run exactly once after a database write.” That sentence combines callback timing with a delivery guarantee. One source about timing cannot automatically support both.

The [Django 5.2 transaction documentation](https://docs.djangoproject.com/en/5.2/topics/db/transactions/#performing-actions-after-commit), checked October 10, 2026, supports a narrower explanation: register a callback within the relevant transaction to defer it until successful commit; rollback discards it. Outside a transaction under autocommit, it runs immediately. Callback failure does not undo an already committed transaction, and an earlier failing callback can prevent later callbacks in that transaction from running under the default behavior.

The editorial decision is to **narrow** the sentence to the documented timing behavior and **reject** the exactly-once delivery claim unless separate evidence establishes it. A related tutorial might still be useful for a worked application, but its subject match does not repair the unsupported guarantee.

You do not need a numeric score for this decision. Write down the exact mismatch. “Source discusses scheduling; draft promises delivery” tells an editor what to fix. “Confidence: 0.91” does not explain the missing support.

When two sources conflict, first check whether they describe different versions, populations, or conditions. Do not average incompatible claims or choose whichever makes the draft easier to finish. If the disagreement remains material, state it or leave the contested claim out.

**Done looks like:** one decision per claim, with a reason an editor can inspect.

<h2 id="hand-off-evidence">5. Hand the writer an evidence record</h2>

Keep research and drafting connected with a short record. This is a proposed editorial checklist, not a feature CiteGuild automatically enforces:

```text
Claim to check:
Scope: version, date, audience, or conditions
Source: title and original URL
Source type: official docs, study, report, or practitioner article
Supporting section: heading and a short paraphrase
Limit or contradiction:
Decision: accept, narrow, reject, or needs further checking
Final sentence:
Checked on:
```

The critical fields are the limitation and final sentence. They keep a writer from expanding a carefully bounded finding into a stronger claim during a later rewrite. An editor should be able to open the URL and reconstruct the decision without rerunning the entire research session.

Place the citation beside the sentence it supports. If a paragraph combines several distinct findings, avoid one trailing link that appears to substantiate all of them. Preserve attribution when describing someone else's experiment or opinion; make your own interpretation recognizable as interpretation.

For developers connecting retrieval to a model, [Anthropic's search-result documentation](https://platform.claude.com/docs/en/build-with-claude/search-results) describes blocks containing a source, title, and text content, with citations enabled explicitly. Its [citation documentation](https://platform.claude.com/docs/en/build-with-claude/citations) describes pointers into supplied documents. Those mechanisms help preserve provenance. They do not independently establish that the original material is correct or that your whole sentence follows from it. CiteGuild does not automatically configure those model-specific citation features.

<h2 id="review-before-publishing">Review after the last rewrite</h2>

Run the source check again on the final prose, not only the first draft. Small edits can change the claim: “can” becomes “will,” a version qualifier disappears, or an observed result becomes a general promise.

Watch for these common failures:

- Citing a search snippet without reading its destination.
- Treating a crawler timestamp as the source's publication date.
- Keeping a link after rewriting the sentence beyond what it supports.
- Using a vendor's claim as independent evidence of market-wide superiority.
- Requiring a citation quota, which encourages marginal sources when none are needed.

A useful stop condition is straightforward: every factual claim you intend to substantiate has support at the scope you wrote, and unresolved claims have been narrowed, removed, or marked for further checking. Keep private notes private; publish the reader-facing explanation and appropriate source links, not your internal research exports.

## Questions before your first search

### Does a relevant search result prove my claim?

No. Relevance helps you choose what to read. Check the original passage and its limits before using it as evidence.

### Can I use this workflow without CiteGuild?

Yes. Use primary documentation, a library, or web search to find candidates, then apply the same claim-level checks. CiteGuild adds access to member-published articles; it does not need to be involved in every research task.

### Does CiteGuild replace Tavily or Exa?

No. Tavily and Exa support web research beyond CiteGuild's participating publishers. Use CiteGuild to discover relevant member articles, official sources for documented behavior, and web search for evidence outside the member network. Read the original source whichever route you use.

### What if I cannot find a supporting source?

Narrow or remove the claim, or label a genuinely interpretive statement as analysis. Do not attach a tangential source to make it look verified.

Already a member? [Open your dashboard](/home), connect your agent, and try one focused search. New to CiteGuild? [Membership is free and invitation-only](/pricing). An existing member can invite you. No source is owed a citation: include it only when it helps the reader.
