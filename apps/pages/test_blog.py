import json
from html import escape

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.core.checks import run_checks
from django.urls import reverse

from apps.pages.services import BLOG_DEFAULT_IMAGE_URL, get_blog_post, list_blog_posts
from citeguild.sitemaps import BlogSitemap, sitemaps

pytestmark = pytest.mark.django_db


@pytest.fixture
def blog_posts_dir(tmp_path, settings):
    settings.BLOG_POSTS_DIR = tmp_path
    settings.SITE_URL = "https://canonical.example"
    return tmp_path


def write_post(blog_posts_dir, slug, frontmatter, body):
    fields = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
    path = blog_posts_dir / f"{slug}.md"
    path.write_text(f"---\n{fields}\n---\n\n{body}\n", encoding="utf-8")
    return path


def test_blog_index_renders_empty_state(client, blog_posts_dir):
    response = client.get(reverse("blog_posts"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "No blog posts available at the moment." in content
    assert 'href="https://canonical.example/blog/"' in content
    escaped_default_image_url = escape(BLOG_DEFAULT_IMAGE_URL, quote=True)
    assert f'property="og:image" content="{escaped_default_image_url}"' in content
    assert 'name="twitter:card" content="summary_large_image"' in content
    assert f'name="twitter:image" content="{escaped_default_image_url}"' in content


def test_blog_post_renders_markdown_and_frontmatter_metadata(client, blog_posts_dir):
    write_post(
        blog_posts_dir,
        "agent-managed-workflows",
        {
            "title": "Agent-managed workflows",
            "description": "How AI agents keep the app current.",
            "published_at": "2026-07-03",
            "updated_at": "2026-07-04",
            "author": "Ada Lovelace",
            "keywords": "[Django, SaaS]",
            "topics": "[agent workflows, deployments]",
            "image": "/static/blog/agent-managed-workflows.png",
            "image_alt": "Agent workflow dashboard",
        },
        "## Why agents need it\n\nAgents need **stable files** for posts.",
    )

    response = client.get(reverse("blog_post", kwargs={"slug": "agent-managed-workflows"}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "<title>Agent-managed workflows | CiteGuild Blog</title>" in content
    assert '<meta name="description" content="How AI agents keep the app current." />' in content
    assert (
        '<link rel="canonical" href="https://canonical.example/blog/agent-managed-workflows" />'
        in content
    )
    assert "<h2>Why agents need it</h2>" in content
    assert "<strong>stable files</strong>" in content
    assert 'property="article:published_time"' in content
    assert 'content="2026-07-03T00:00:00+00:00"' in content
    assert (
        'property="og:image" content="https://canonical.example/static/blog/agent-managed-workflows.png"'
        in content
    )
    assert "Agent workflow dashboard" in content
    assert '"@type": "BlogPosting"' in content
    assert '"datePublished": "2026-07-03T00:00:00+00:00"' in content


def test_blog_posts_are_sorted_by_publication_date(blog_posts_dir):
    write_post(
        blog_posts_dir,
        "older-post",
        {
            "title": "Older post",
            "description": "Older description.",
            "published_at": "2026-07-01",
        },
        "Older body.",
    )
    write_post(
        blog_posts_dir,
        "newer-post",
        {
            "title": "Newer post",
            "description": "Newer description.",
            "published_at": "2026-07-03",
        },
        "Newer body.",
    )

    assert [post.slug for post in list_blog_posts()] == ["newer-post", "older-post"]


def test_blog_post_absolute_url_uses_django_method_convention(blog_posts_dir):
    write_post(
        blog_posts_dir,
        "method-post",
        {
            "title": "Method post",
            "description": "Method description.",
            "published_at": "2026-07-03",
        },
        "Method body.",
    )

    post = get_blog_post("method-post")

    assert post.get_absolute_url() == "/blog/method-post"


def test_blog_index_skips_invalid_markdown_files(client, blog_posts_dir, caplog):
    write_post(
        blog_posts_dir,
        "valid-post",
        {
            "title": "Valid post",
            "description": "Valid description.",
            "published_at": "2026-07-03",
        },
        "Valid body.",
    )
    (blog_posts_dir / "invalid-post.md").write_text(
        "---\ntitle: Missing description\npublished_at: 2026-07-03\n---\n\nInvalid body.\n",
        encoding="utf-8",
    )

    with caplog.at_level("WARNING", logger="apps.pages.services"):
        response = client.get(reverse("blog_posts"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Valid post" in content
    assert "Invalid body" not in content
    record = next(record for record in caplog.records if record.name == "apps.pages.services")
    assert record.getMessage() == "blog.post.load.completed"
    assert getattr(record, "event.name") == "blog.post.load.completed"
    assert record.post_slug == "invalid-post"
    assert record.outcome == "failure"
    assert getattr(record, "error.type") == "BlogPostValidationError"


def test_blog_post_404s_when_markdown_file_is_missing(client, blog_posts_dir):
    response = client.get(reverse("blog_post", kwargs={"slug": "missing-post"}))

    assert response.status_code == 404


def test_blog_post_404s_when_frontmatter_is_invalid(client, blog_posts_dir):
    (blog_posts_dir / "invalid-post.md").write_text(
        "---\n"
        "title: Invalid post\n"
        "description: Invalid description.\n"
        "published_at: not-a-date\n"
        "---\n\n"
        "Body.\n",
        encoding="utf-8",
    )

    response = client.get(reverse("blog_post", kwargs={"slug": "invalid-post"}))

    assert response.status_code == 404


def test_blog_frontmatter_check_reports_missing_seo_fields(blog_posts_dir):
    (blog_posts_dir / "missing-description.md").write_text(
        "---\ntitle: Missing description\npublished_at: 2026-07-03\n---\n\nBody.\n",
        encoding="utf-8",
    )

    errors = [error for error in run_checks() if error.id == "blog.E001"]

    assert len(errors) == 1
    assert "missing required frontmatter: description" in errors[0].msg


def test_blog_sitemap_uses_markdown_posts(blog_posts_dir):
    write_post(
        blog_posts_dir,
        "sitemap-post",
        {
            "title": "Sitemap post",
            "description": "Sitemap description.",
            "published_at": "2026-07-03",
            "updated_at": "2026-07-04",
        },
        "Sitemap body.",
    )

    sitemap = BlogSitemap()
    post = sitemap.items()[0]

    assert sitemap.location(post) == "/blog/sitemap-post"
    assert sitemap.lastmod(post).isoformat() == "2026-07-04T00:00:00+00:00"


def test_blog_sitemap_uses_site_url_and_last_modified_header(rf, blog_posts_dir):
    write_post(
        blog_posts_dir,
        "sitemap-post",
        {
            "title": "Sitemap post",
            "description": "Sitemap description.",
            "published_at": "2026-07-03",
            "updated_at": "2026-07-04",
        },
        "Sitemap body.",
    )

    request = rf.get("/sitemap.xml")
    request.user = AnonymousUser()

    response = sitemap_view(request, {"blog": sitemaps["blog"]})
    response.render()

    assert response.status_code == 200
    assert response.headers["Last-Modified"]
    assert b"https://canonical.example/blog/sitemap-post" in response.content


def test_blog_post_schema_uses_checked_in_markdown_content(blog_posts_dir):
    write_post(
        blog_posts_dir,
        "schema-post",
        {
            "title": "Schema post",
            "description": "Schema description.",
            "published_at": "2026-07-03",
        },
        "The article body comes from markdown.",
    )

    post = get_blog_post("schema-post")
    schema = json.loads(post_schema_json(post))

    assert schema["headline"] == "Schema post"
    assert schema["url"] == "https://canonical.example/blog/schema-post"
    assert schema["articleBody"] == "The article body comes from markdown."


def post_schema_json(post):
    from apps.pages.services import blog_post_schema, json_ld

    return json_ld(blog_post_schema(post))
