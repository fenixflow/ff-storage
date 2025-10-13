"""
Markdown rendering utilities for document ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from markdown_it import MarkdownIt

from ..base import ParseOptions
from ..models import BundleNode, ExtractedDocument, ExtractedTable


@dataclass(slots=True)
class RendererContext:
    """Options passed to the Markdown renderer."""

    renderer: str
    attachment_root: Optional[Path]


class MarkdownRenderer:
    """Compose Markdown output for parsed documents and attachments."""

    def __init__(self, *, default_renderer: str = "auto") -> None:
        self._default_renderer = default_renderer
        self._markdown_it = MarkdownIt()  # Used for basic normalisation when requested.

    def render(
        self,
        document: ExtractedDocument,
        root_node: BundleNode,
        options: ParseOptions,
    ) -> BundleNode:
        """
        Populate the root node (and attachments) with Markdown content.

        Args:
            document: Extracted document payload from the parser.
            root_node: Root bundle node representing the source file.
            options: Parse/render options.
        """
        ctx = RendererContext(
            renderer=options.renderer or self._default_renderer, attachment_root=None
        )

        if document.email_metadata:
            root_node.markdown = self._render_email(document, ctx)
        else:
            root_node.markdown = self._render_generic(document, ctx)

        # Attach previously collected attachments and render markdown for each.
        root_node.children = []
        self._attach_children(root_node, document.attachments)

        for attachment in root_node.children:
            self._render_attachment_tree(attachment, ctx)

        return root_node

    def _render_email(self, document: ExtractedDocument, ctx: RendererContext) -> str:
        """Render Markdown tailored for email documents."""
        meta = document.email_metadata
        lines: List[str] = []

        if meta:
            lines.append("# Email")
            lines.append("")
            lines.extend(self._render_metadata_table(meta))
            lines.append("")

        body_segments = document.metadata.custom_properties.get("email_body_segments") or []
        body_text = "\n\n".join(segment for segment in body_segments if segment)
        if not body_text and document.text:
            body_text = document.text

        if body_text:
            lines.append("## Body")
            lines.append("")
            lines.append(body_text)

        attachments_section = self._render_attachments_section(document.attachments)
        if attachments_section:
            lines.append("")
            lines.append(attachments_section)

        return "\n".join(lines).strip()

    def _render_generic(self, document: ExtractedDocument, ctx: RendererContext) -> str:
        """Render Markdown for non-email documents."""
        lines: List[str] = []

        if document.metadata.title:
            lines.append(f"# {document.metadata.title}")
        elif document.file_path:
            lines.append(f"# {Path(document.file_path).name}")

        body_sections = self._render_page_sections(document)
        if body_sections:
            if lines:
                lines.append("")
            lines.extend(body_sections)
        elif document.text:
            if lines:
                lines.append("")
            lines.append(document.text)

        table_sections = self._render_tables(document.tables)
        if table_sections:
            lines.append("")
            lines.extend(table_sections)

        attachments_section = self._render_attachments_section(document.attachments)
        if attachments_section:
            lines.append("")
            lines.append(attachments_section)

        markdown = "\n".join(lines).strip()
        if ctx.renderer == "markdownit":
            # Round trip through markdown-it to normalise spacing and headings.
            tokens = self._markdown_it.parse(markdown or "")
            markdown = self._markdown_it.renderer.render(tokens, self._markdown_it.options, {})
        return markdown

    def _render_page_sections(self, document: ExtractedDocument) -> List[str]:
        """Render per-page sections when page metadata is available."""
        sections: List[str] = []
        for page in document.pages:
            if page.page:
                sections.append(f"## Page {page.page}")
                sections.append("")
            sections.append(page.content)
            sections.append("")
        return [section for section in sections if section.strip()]

    def _render_tables(self, tables: Iterable[ExtractedTable]) -> List[str]:
        """Render simple Markdown tables."""
        sections: List[str] = []
        for index, table in enumerate(tables, start=1):
            sections.append(f"## Table {index}")
            sections.append("")
            header_row = "| " + " | ".join(table.headers) + " |"
            divider = "| " + " | ".join(["---"] * len(table.headers)) + " |"
            sections.append(header_row)
            sections.append(divider)
            for row in table.rows:
                sections.append("| " + " | ".join(row) + " |")
            sections.append("")
        return [section for section in sections if section.strip()]

    def _render_attachments_section(self, attachments: Iterable[BundleNode]) -> str:
        """Render an attachments listing."""
        rows: List[str] = []
        for node in attachments:
            link_label = node.location or node.name
            if not link_label:
                continue
            descriptor = node.mime_type or node.file_type or ""
            rows.append(f"- [{node.name}]({link_label}){f' — {descriptor}' if descriptor else ''}")
            if node.children:
                for child in node.children:
                    child_label = child.location or child.name
                    descriptor = child.mime_type or child.file_type or ""
                    rows.append(
                        f"  - [{child.name}]({child_label})"
                        f"{f' — {descriptor}' if descriptor else ''}"
                    )
        if not rows:
            return ""
        return "## Attachments\n\n" + "\n".join(rows)

    def _render_metadata_table(self, meta) -> List[str]:
        """Render email metadata as a Markdown table."""
        rows: List[str] = ["| Field | Value |", "| --- | --- |"]
        if meta.from_address:
            rows.append(f"| From | {meta.from_address} |")
        if meta.to_addresses:
            rows.append(f"| To | {', '.join(meta.to_addresses)} |")
        if meta.cc_addresses:
            rows.append(f"| Cc | {', '.join(meta.cc_addresses)} |")
        if meta.subject:
            rows.append(f"| Subject | {meta.subject} |")
        if meta.date:
            rows.append(f"| Date | {meta.date.isoformat()} |")
        return rows

    def _render_attachment_tree(self, node: BundleNode, ctx: RendererContext) -> None:
        """Recursively populate attachment markdown when missing."""
        if node.markdown is None:
            descriptor = node.mime_type or node.file_type or "attachment"
            node.markdown = f"Attachment: {node.name} ({descriptor})"
        for child in node.children:
            self._render_attachment_tree(child, ctx)

    def _attach_children(self, parent: BundleNode, children: Iterable[BundleNode]) -> None:
        """Attach a list of nodes to a parent using BundleNode.add_child."""
        for child in children:
            self._attach_node(parent, child)

    def _attach_node(self, parent: BundleNode, node: BundleNode) -> None:
        """Attach a node to a parent and recursively fix depth/parent metadata."""
        descendants = list(node.children)
        node.children = []
        parent.add_child(node)
        for descendant in descendants:
            self._attach_node(node, descendant)
