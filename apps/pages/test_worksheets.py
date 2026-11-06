"""Download safety and source-parity contracts, without a database or live services."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.pages.views import research_methods_worksheet_view, source_evidence_worksheet_view


@pytest.fixture(
    params=[
        (
            "original-research-methods-template",
            "research_methods_worksheet",
            research_methods_worksheet_view,
            "methods",
            "[specific question]",
        ),
        (
            "find-sources-ai-writing",
            "source_evidence_worksheet",
            source_evidence_worksheet_view,
            "evidence",
            "[one checkable statement]",
        ),
    ],
    ids=["publisher-methods", "source-evidence"],
)
def worksheet_case(request):
    return request.param


def test_public_worksheet_download_uses_published_fields(rf, settings, tmp_path, worksheet_case):
    slug, route, view, section, field = worksheet_case
    settings.SITE_URL = "https://canonical.example"
    source = (settings.BASE_DIR / f"apps/pages/posts/{slug}.md").read_text()
    source = source.replace(field, "[a revised question or claim]")
    if section == "methods":
        source = source.replace("[wording]", "[a revised survey question]")
    (tmp_path / f"{slug}.md").write_text(source)
    settings.BLOG_POSTS_DIR = tmp_path
    path = reverse(route)
    request = rf.get(path)
    request.user = AnonymousUser()
    response = view(request)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/markdown; charset=utf-8"
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Robots-Tag"] == "noindex"
    content = response.content.decode()
    assert f"https://canonical.example/blog/{slug}" in content
    assert "[a revised question or claim]" in content
    if section == "methods":
        assert "[completed runs, errors and timeouts]" in content
        assert "[a revised survey question]" in content
        assert "[unweighted eligible count]" in content
        assert "does not validate a study" in content
    else:
        assert "independence unknown" in content
        assert "not an automatic fact-checker" in content
        assert "Original evidence" in content
    assert "not submit it" in content
    assert "<svg" not in content
    assert "<!-- worksheet:" not in content


@pytest.mark.parametrize("invalid", ["missing", "unclosed", "unquoted"])
def test_worksheet_fails_closed_if_source_blocks_are_invalid(
    rf, settings, tmp_path, invalid, worksheet_case
):
    from django.http import Http404

    slug, route, view, section, _ = worksheet_case
    source = (settings.BASE_DIR / f"apps/pages/posts/{slug}.md").read_text()
    if invalid == "missing":
        source = source.replace(f"<!-- worksheet:{section}:start -->", "")
    elif invalid == "unclosed":
        source = source.replace(f"<!-- worksheet:{section}:end -->", "")
    else:
        source = source.replace(
            "> **Question and intended use:**" if section == "methods" else "> **Claim to check:**",
            "Private research: not a template",
        )
    (tmp_path / f"{slug}.md").write_text(source)
    settings.BLOG_POSTS_DIR = tmp_path

    with pytest.raises(Http404):
        view(rf.get(reverse(route)))


def test_worksheet_rejects_submitted_research(rf, worksheet_case):
    _, route, view, _, _ = worksheet_case
    response = view(rf.post(reverse(route)))
    assert response.status_code == 405
