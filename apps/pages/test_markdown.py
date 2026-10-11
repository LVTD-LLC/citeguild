from xml.etree import ElementTree

import markdown

from apps.pages.markdown import ScrollableTablesExtension


def render(content):
    return markdown.markdown(content, extensions=["tables", ScrollableTablesExtension()])


def test_tables_keep_semantics_and_content_inside_named_keyboard_regions():
    html = render(
        "Before.\n\n| Option | Fit |\n| --- | --- |\n"
        "| [CiteGuild](/pricing) | Source discovery |\n\n"
        "Between.\n\n| Other | Fit |\n| --- | --- |\n| Digest | Requests |\n\nAfter."
    )
    root = ElementTree.fromstring(f"<article>{html}</article>")
    regions = root.findall("./div")
    assert len(regions) == 2
    for number, region in enumerate(regions, start=1):
        assert region.attrib == {
            "class": "blog-table-scroll app-focus",
            "role": "region",
            "tabindex": "0",
            "aria-label": f"Article table {number}, scroll to see all columns",
        }
        table = region.find("./table")
        assert table is not None
        assert len(table.findall("./thead/tr/th[@scope='col']")) == 2
        assert len(table.findall("./tbody/tr/td")) == 2
    assert root.find(".//a").attrib["href"] == "/pricing"
    assert [p.text for p in root.findall("./p")] == ["Before.", "Between.", "After."]


def test_table_free_articles_are_unchanged():
    content = "## Source selection\n\nRead **every source** before citing it."
    assert render(content) == markdown.markdown(content, extensions=["tables"])
