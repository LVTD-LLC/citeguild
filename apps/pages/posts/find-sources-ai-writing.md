---
title: "Find Sources for AI Writing"
description: "Find sources for AI writing, check what each article supports, and give your agent a practical evidence checklist before it adds a citation."
published_at: "2026-10-10"
updated_at: "2026-10-10"
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
  - question: "What if I cannot find a supporting source?"
    answer: "Narrow or remove the claim, or label a genuinely interpretive statement as analysis. Do not attach a tangential source to make it look verified."
---

To find sources for AI writing, start with the claim you need to support. Choose the right kind of source, retrieve candidates, and read the original passage before citing it. Give your agent the source URL, relevant context, and limits of the evidence, not a list of links to decorate a finished draft.

This workflow is for agents writing technical articles, SaaS guides, and other editorial content. You can use it with ordinary web research. The CiteGuild example requires an installed CLI and an existing member account; the source-selection method does not.

**The short version:**

1. Write one checkable claim.
2. Choose primary evidence or editorial context according to the question.
3. Retrieve a small set of candidates and open the sources.
4. Accept, narrow, or reject the claim based on what you read.
5. Keep that decision beside the citation through the final edit.

On this page: [frame the claim](#frame-the-claim), [choose sources](#choose-sources), [search with an agent](#search-with-an-agent), [check support](#check-support), [hand off evidence](#hand-off-evidence), and [review before publishing](#review-before-publishing).

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

For a CiteGuild member using a shell-based agent, this is a focused search example. Have your environment supply `CITEGUILD_API_KEY` securely; do not put a real key into a prompt, command history, or published example.

```bash
citeguild search --api-base https://citeguild.com/api \
  --json --limit 10 --language en \
  --exclude-domain your-site.example \
  "How do Django transaction commit hooks work?"
```

Replace `your-site.example` with your own site's hostname if you want to exclude it. Put options before the query. The explicit API address makes the destination clear instead of relying on the default in your installed CLI version.

The command follows the [official CiteGuild CLI contract](https://github.com/LVTD-LLC/citeguild/blob/3f92cd8be7ebf29d948a0f7fb82f7cb741e1d8a3/cli/README.md), checked against that repository revision on October 10, 2026. It is a source-checked usage example, not a transcript of a live member search. [Member CLI setup](/docs/features/cli/) requires sign-in. MCP and API clients expose the same v1 search contract, so the review below applies to them too.

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

### What if I cannot find a supporting source?

Narrow or remove the claim, or label a genuinely interpretive statement as analysis. Do not attach a tangential source to make it look verified.

Already a member? [Open your dashboard](/home), connect your agent, and try one focused search. New to CiteGuild? [Membership is free and invitation-only](/pricing). An existing member can invite you. No source is owed a citation: include it only when it helps the reader.
