"""Presentation for repository-owned blog Markdown."""

from xml.etree import ElementTree

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor


class ScrollableTables(Treeprocessor):
    def run(self, root):
        table_number = 0
        for parent in list(root.iter()):
            for index, child in enumerate(list(parent)):
                if child.tag != "table":
                    continue
                table_number += 1
                wrapper = ElementTree.Element(
                    "div",
                    {
                        "class": "blog-table-scroll app-focus",
                        "role": "region",
                        "tabindex": "0",
                        "aria-label": f"Article table {table_number}, scroll to see all columns",
                    },
                )
                wrapper.tail, child.tail = child.tail, None
                parent.remove(child)
                parent.insert(index, wrapper)
                wrapper.append(child)
                for heading in child.findall("./thead/tr/th"):
                    heading.set("scope", "col")
        return root


class ScrollableTablesExtension(Extension):
    def extendMarkdown(self, md):
        md.treeprocessors.register(ScrollableTables(md), "scrollable_tables", 5)
