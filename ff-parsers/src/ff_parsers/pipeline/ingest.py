"""
Document ingestion pipeline that normalises parser output into Markdown bundles.
"""

from __future__ import annotations

import tempfile
import hashlib
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Union

from ..base import ParseOptions
from ..exceptions import ParserError, UnsupportedFormatError
from ..factory import ParserFactory
from ..models import BundleNode, DocumentBundle, ExtractedDocument
from ..renderers.markdown import MarkdownRenderer
from ..renderers.markitdown import MarkItDownFallback
from ..utils.attachments import compute_sha256, ensure_directory, persist_attachment_bytes


class DocumentIngestionPipeline:
    """
    High-level pipeline that accepts an input file, runs the appropriate parser,
    persists attachments, and returns a manifest + Markdown bundle.
    """

    def __init__(
        self,
        *,
        parser_factory: Optional[ParserFactory] = None,
        renderer: Optional[MarkdownRenderer] = None,
    ) -> None:
        self._factory = parser_factory or ParserFactory()
        self._renderer = renderer or MarkdownRenderer()
        self._markitdown = MarkItDownFallback()

    def ingest(
        self,
        source: Union[str, Path, bytes],
        options: Optional[ParseOptions] = None,
        *,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> DocumentBundle:
        """
        Ingest a document from disk or in-memory bytes and return a DocumentBundle.

        Args:
            source: Path to the file or raw bytes.
            options: Parsing options (defaults to ParseOptions()).
            output_dir: Optional directory where attachments should be persisted.
        """
        options = options or ParseOptions()
        temp_file: Optional[tempfile.NamedTemporaryFile] = None
        path: Optional[Path] = None

        try:
            if isinstance(source, (str, Path)):
                path = Path(source)
            elif isinstance(source, bytes):
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
                temp_file.write(source)
                temp_file.flush()
                path = Path(temp_file.name)
            else:
                raise TypeError(f"Unsupported source type: {type(source)!r}")

            if not path.exists():
                raise FileNotFoundError(f"Source path does not exist: {path}")

            if options.renderer == "markitdown":
                if self._markitdown.available:
                    return self._ingest_with_markitdown(path, options)
                raise ParserError(
                    "MarkItDown renderer requested but markitdown package is not installed."
                )

            try:
                parser = self._factory.get_parser_for_file(path)
            except UnsupportedFormatError:
                if self._markitdown.available:
                    return self._ingest_with_markitdown(path, options)
                raise

            try:
                document = parser.parse(path, options)
            except ParserError as exc:
                if self._markitdown.available:
                    return self._ingest_with_markitdown(path, options, error=exc)
                raise

            attachments_dir: Optional[Path] = None
            if document.attachments:
                attachments_dir = self._resolve_attachments_dir(options, output_dir, base_path=path)
                ensure_directory(attachments_dir)
                self._persist_attachments(document.attachments, attachments_dir, options)

            root_node = self._build_root_node(path, document, attachments_dir)
            rendered_root = self._renderer.render(document, root_node, options)

            if not options.include_binary_payloads:
                self._strip_binary_payloads(rendered_root)

            options_payload = self._options_to_dict(options)
            return DocumentBundle(
                document=rendered_root,
                attachments_dir=str(attachments_dir) if attachments_dir else None,
                source_path=str(path),
                options=options_payload,
            )

        finally:
            if temp_file is not None:
                temp_path = Path(temp_file.name)
                temp_file.close()
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)

    def _ingest_with_markitdown(
        self,
        path: Path,
        options: ParseOptions,
        error: Optional[Exception] = None,
    ) -> DocumentBundle:
        """Fallback ingestion path using markitdown."""
        markdown = self._markitdown.render_path(path)
        file_hash = self._hash_file(path)
        stat = path.stat()

        root = BundleNode(
            name=path.name,
            file_type=path.suffix,
            markdown=markdown,
            mime_type=None,
            sha256=file_hash,
            size_bytes=stat.st_size,
            source_path=str(path),
            kind="document",
            metadata={
                "origin": "markitdown",
                "error": str(error) if error else None,
                "metadata": {
                    "file_size": stat.st_size,
                },
            },
        )

        return DocumentBundle(
            document=root,
            attachments_dir=None,
            source_path=str(path),
            options=self._options_to_dict(options),
        )

    def _options_to_dict(self, options: ParseOptions) -> Dict[str, object]:
        """Convert ParseOptions (dataclass) to a serialisable dictionary."""
        if is_dataclass(options):
            return asdict(options)
        raise ParserError("ParseOptions must remain a dataclass instance.")

    def _resolve_attachments_dir(
        self,
        options: ParseOptions,
        output_dir: Optional[Union[str, Path]],
        *,
        base_path: Optional[Path],
    ) -> Optional[Path]:
        """Determine where attachments should be persisted."""
        if options.attachment_root:
            return Path(options.attachment_root)
        if output_dir:
            return Path(output_dir) / "attachments"
        if base_path:
            return base_path.parent / f"{base_path.stem}_attachments"
        return Path(tempfile.mkdtemp(prefix="ff-attachments-"))

    def _persist_attachments(
        self,
        attachments: Iterable[BundleNode],
        attachments_dir: Path,
        options: ParseOptions,
    ) -> None:
        """Persist attachment binaries to disk recursively."""
        dedupe: Dict[str, Path] = {}
        for node in attachments:
            self._persist_attachment_node(node, attachments_dir, options, dedupe)

    def _persist_attachment_node(
        self,
        node: BundleNode,
        attachments_dir: Path,
        options: ParseOptions,
        dedupe: Dict[str, Path],
    ) -> None:
        payload = node.binary
        if payload is not None:
            if node.sha256 is None:
                node.sha256 = compute_sha256(payload)
            if node.sha256 in dedupe:
                path = dedupe[node.sha256]
            else:
                filename = node.name or f"attachment-{node.sha256[:8]}"
                path = persist_attachment_bytes(payload, attachments_dir, filename)
                dedupe[node.sha256] = path
            node.metadata["absolute_path"] = str(path)
            node.location = self._relative_location(path, attachments_dir)
            if not options.include_binary_payloads:
                node.binary = None

        for child in node.children:
            self._persist_attachment_node(child, attachments_dir, options, dedupe)

    def _relative_location(self, path: Path, attachments_dir: Path) -> str:
        """Return a stable relative path for manifest representation."""
        try:
            relative = path.relative_to(attachments_dir.parent)
        except ValueError:
            relative = path.name
        return str(relative)

    def _strip_binary_payloads(self, node: BundleNode) -> None:
        """Remove binary payloads from all nodes."""
        node.binary = None
        for child in node.children:
            self._strip_binary_payloads(child)

    def _build_root_node(
        self,
        path: Path,
        document: ExtractedDocument,
        attachments_dir: Optional[Path],
    ) -> BundleNode:
        """Construct the root bundle node for the primary document."""
        name = path.name
        root = BundleNode(
            name=name,
            file_type=path.suffix,
            mime_type=document.metadata.mime_type,
            sha256=document.file_hash,
            size_bytes=document.metadata.file_size,
            source_path=str(path),
            kind="document",
            metadata={
                "parser_version": document.parser_version,
                "extraction_timestamp": (
                    document.extraction_timestamp.isoformat()
                    if document.extraction_timestamp
                    else None
                ),
                "attachments_root": str(attachments_dir) if attachments_dir else None,
                "metadata": document.metadata.model_dump(),
                "email_metadata": (
                    document.email_metadata.model_dump() if document.email_metadata else None
                ),
                "counts": {
                    "pages": document.page_count,
                    "tables": document.table_count,
                    "images": document.image_count,
                    "attachments": len(document.attachments),
                },
            },
        )
        return root

    def _hash_file(self, path: Path) -> str:
        """Compute a SHA-256 hash for a file without loading it entirely into memory."""
        sha = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()
