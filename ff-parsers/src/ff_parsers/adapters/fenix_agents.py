"""
Adapter for exposing the ingestion pipeline to fenix-agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from ..base import ParseOptions
from ..models import DocumentBundle
from ..pipeline.ingest import DocumentIngestionPipeline


@dataclass
class ParsedDocumentAdapter:
    """ParsedDocument-compatible payload for fenix-agents."""

    content: str
    metadata: dict[str, Any]
    source_file: str
    word_count: int = 0
    has_tables: bool = False
    has_images: bool = False
    manifest: Optional[dict[str, Any]] = None
    attachments_dir: Optional[str] = None
    bundle: Optional[DocumentBundle] = None

    def __post_init__(self) -> None:
        if not self.word_count and self.content:
            self.word_count = len(self.content.split())
        if not self.has_tables and self.content:
            self.has_tables = "|" in self.content and "\n|" in self.content
        if not self.has_images and self.content:
            self.has_images = "![" in self.content


class FenixAgentsPipelineAdapter:
    """Thin wrapper that returns ParsedDocumentAdapter instances."""

    def __init__(self, *, pipeline: Optional[DocumentIngestionPipeline] = None) -> None:
        self._pipeline = pipeline or DocumentIngestionPipeline()

    def ingest(
        self,
        file_path: Union[str, Path],
        options: Optional[ParseOptions] = None,
    ) -> ParsedDocumentAdapter:
        """Parse a file and produce a ParsedDocument-compatible object."""
        bundle = self._pipeline.ingest(Path(file_path), options)
        metadata = self._build_metadata(bundle)
        manifest = bundle.to_manifest(include_binary=False)
        counts = metadata.get("counts", {})
        document_meta = metadata.get("document_metadata", {})

        return ParsedDocumentAdapter(
            content=bundle.markdown,
            metadata=metadata,
            source_file=bundle.source_path or str(file_path),
            word_count=document_meta.get("word_count", 0),
            has_tables=counts.get("tables", 0) > 0,
            has_images=counts.get("images", 0) > 0,
            manifest=manifest,
            attachments_dir=bundle.attachments_dir,
            bundle=bundle,
        )

    def _build_metadata(self, bundle: DocumentBundle) -> dict[str, Any]:
        """Assemble metadata dictionary consumed by fenix-agents."""
        document_meta = bundle.document.metadata.get("metadata", {})
        counts = bundle.document.metadata.get("counts", {})
        metadata: dict[str, Any] = {
            "document_metadata": document_meta,
            "parser_version": bundle.document.metadata.get("parser_version"),
            "bundle_created_at": bundle.created_at.isoformat(),
            "attachments_dir": bundle.attachments_dir,
            "attachment_count": sum(1 for _ in bundle.iter_attachments()),
            "counts": counts,
        }
        return metadata
