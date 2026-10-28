"""Public, blank worksheets derived from the corresponding published guide."""

from apps.pages.services import BlogPostValidationError, get_blog_post


def _worksheet_fields(content: str, section: str) -> str:
    start = f"<!-- worksheet:{section}:start -->"
    end = f"<!-- worksheet:{section}:end -->"
    if content.count(start) != 1 or content.count(end) != 1:
        raise BlogPostValidationError("Worksheet section is unavailable")
    _, _, remainder = content.partition(start)
    fields, separator, _ = remainder.partition(end)
    lines = fields.strip().splitlines()
    if not separator or not lines or any(line and not line.startswith(">") for line in lines):
        raise BlogPostValidationError("Worksheet section is invalid")
    return "\n".join(line.removeprefix(">").removeprefix(" ") for line in lines)


def research_methods_worksheet() -> str:
    post = get_blog_post("original-research-methods-template")
    methods = _worksheet_fields(post.content, "methods")
    benchmark = _worksheet_fields(post.content, "benchmark")
    return (
        "# CiteGuild publisher research worksheet\n\n"
        f"Guide: {post.canonical_url}\n"
        f"Guide updated: {post.updated_at.date().isoformat()}\n\n"
        "Save a copy and replace bracketed fields with what you actually did. "
        "Explain any field that does not apply. Complete the general methods record; "
        "keep the benchmark addendum only for a technical performance study. "
        "For surveys, also use the survey guidance in the linked article.\n\n"
        "This blank worksheet does not validate a study, establish representativeness, "
        "prove causation or guarantee a citation. Keep confidential evidence and personal "
        "data out of published copies. Filling in this local file does not submit it "
        "to CiteGuild.\n\n"
        f"## General methods record\n\n{methods}\n\n"
        f"## Optional technical-benchmark addendum\n\n{benchmark}\n"
    )
