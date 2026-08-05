import json
from datetime import UTC, datetime

from apps.pages.services import (
    article_schema,
    breadcrumb_list_schema,
    faq_page_schema,
    json_ld,
)


def test_faq_page_schema_serializes_questions_and_escapes_script_end(settings):
    settings.SITE_URL = "https://citeguild.example"

    payload = faq_page_schema([("Can I add a sitemap?", "Yes. </script>")])
    serialized = json_ld(payload)
    parsed = json.loads(serialized)

    assert "</script>" not in serialized
    assert parsed["@type"] == "FAQPage"
    assert parsed["mainEntity"][0]["acceptedAnswer"]["text"] == "Yes. </script>"


def test_breadcrumb_list_schema_builds_absolute_ordered_items(settings):
    settings.SITE_URL = "https://citeguild.example"

    schema = breadcrumb_list_schema([("Home", "/"), ("Alternatives", "/alternatives/featured")])

    assert schema["itemListElement"] == [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": "https://citeguild.example/",
        },
        {
            "@type": "ListItem",
            "position": 2,
            "name": "Alternatives",
            "item": "https://citeguild.example/alternatives/featured",
        },
    ]


def test_article_schema_uses_public_url_and_publisher(settings):
    settings.SITE_URL = "https://citeguild.example"
    published_at = datetime(2026, 8, 5, tzinfo=UTC)

    schema = article_schema(
        headline="Editorial source discovery",
        description="A practical guide.",
        path="/playbooks/editorial-source-discovery",
        date_published=published_at,
        date_modified=published_at,
    )

    assert schema["@type"] == "Article"
    assert schema["url"] == ("https://citeguild.example/playbooks/editorial-source-discovery")
    assert schema["publisher"]["@type"] == "Organization"
    assert schema["datePublished"] == "2026-08-05T00:00:00+00:00"
