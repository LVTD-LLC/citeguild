# Pages Content Instructions

These rules apply when editing repository-tracked content owned by `apps/pages`,
including `apps/pages/content/docs`, docs navigation, docs views, and docs
templates. Root engineering guidance still comes from the project `AGENTS.md`.

## Audience

- Write for CiteGuild users first, not for maintainers.
- Start with what the user can accomplish and why it matters.
- Use plain language, concrete nouns, and product terms that appear in the UI.
- Avoid implementation detail unless the reader needs it to complete the task.

## Structure

- Put the most important action or concept first.
- Use headings that describe the outcome, not vague labels.
- Keep paragraphs short and scannable.
- Use numbered lists for ordered workflows and bullets for unordered choices.
- Include expected results, important caveats, and recovery steps for failure
  states.

## Examples

- Keep examples consistent with the generated project structure.
- Use environment variables, URLs, and API keys as placeholders unless the value
  is safe and generic.
- Do not include real user data, secrets, private domains, or maintainer-specific
  names.
- For code blocks, prefer copy-ready commands that work from the repository root.

## Validation

- Update `apps/pages/content/docs/navigation.yaml` when adding or removing docs pages.
- Check that slugs, side navigation, table-of-contents links, and code-copy
  behavior still render correctly.
- If a docs page describes product behavior, update it in the same change as the
  behavior.
