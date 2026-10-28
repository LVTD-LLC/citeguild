"""Download safety and source-parity contracts, without a database or live services."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.pages.views import research_methods_worksheet_view


def test_public_worksheet_download_uses_published_fields(rf, settings, tmp_path):
    settings.SITE_URL = "https://canonical.example"
    source = (
        settings.BASE_DIR / "apps/pages/posts/original-research-methods-template.md"
    ).read_text()
    source = source.replace("[specific question]", "[a revised research question]")
    (tmp_path / "original-research-methods-template.md").write_text(source)
    settings.BLOG_POSTS_DIR = tmp_path
    path = reverse("research_methods_worksheet")
    request = rf.get(path)
    request.user = AnonymousUser()
    response = research_methods_worksheet_view(request)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/markdown; charset=utf-8"
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Robots-Tag"] == "noindex"
    content = response.content.decode()
    assert "https://canonical.example/blog/original-research-methods-template" in content
    assert "[a revised research question]" in content
    assert "[completed runs, errors and timeouts]" in content
    assert "does not validate a study" in content
    assert "Filling in this local file does not submit it" in content
    assert "<svg" not in content
    assert "worksheet:methods" not in content


@pytest.mark.parametrize("invalid", ["missing", "unclosed", "unquoted"])
def test_worksheet_fails_closed_if_source_blocks_are_invalid(rf, settings, tmp_path, invalid):
    from django.http import Http404

    source = (
        settings.BASE_DIR / "apps/pages/posts/original-research-methods-template.md"
    ).read_text()
    if invalid == "missing":
        source = source.replace("<!-- worksheet:methods:start -->", "")
    elif invalid == "unclosed":
        source = source.replace("<!-- worksheet:benchmark:end -->", "")
    else:
        source = source.replace(
            "> **Question and intended use:**", "Private research: not a template"
        )
    (tmp_path / "original-research-methods-template.md").write_text(source)
    settings.BLOG_POSTS_DIR = tmp_path

    with pytest.raises(Http404):
        research_methods_worksheet_view(rf.get(reverse("research_methods_worksheet")))


def test_worksheet_rejects_submitted_research(rf):
    response = research_methods_worksheet_view(rf.post(reverse("research_methods_worksheet")))
    assert response.status_code == 405
