"""
Document ingestion pipeline that normalises parser output into Markdown bundles.
"""

from __future__ import annotations

import hashlib
import tempfile
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
from ..utils.temp_file_manager import managed_temp_file


class DocumentIngestionPipeline:
    """
    High-level pipeline that accepts an input file, runs the appropriate parser,
    persists attachments, and returns a manifest + Markdown bundle.
    """

    # Thresholds for detecting scanned PDFs
    SCANNED_PDF_TEXT_LENGTH_THRESHOLD = 100
    SCANNED_PDF_WORD_COUNT_THRESHOLD = 20

    def __init__(
        self,
        *,
        parser_factory: Optional[ParserFactory] = None,
        renderer: Optional[MarkdownRenderer] = None,
    ) -> None:
        self._factory = parser_factory or ParserFactory()
        self._renderer = renderer or MarkdownRenderer()
        self._markitdown = MarkItDownFallback()

    def _is_likely_scanned_pdf(self, markdown_text: str) -> bool:
        """
        Check if a PDF is likely scanned based on extracted text length and word count.

        Args:
            markdown_text: The extracted markdown text from the PDF

        Returns:
            True if the PDF is likely scanned (too little text), False otherwise
        """
        text_length = len(markdown_text.strip())
        word_count = len(markdown_text.split())
        return (
            text_length < self.SCANNED_PDF_TEXT_LENGTH_THRESHOLD
            or word_count < self.SCANNED_PDF_WORD_COUNT_THRESHOLD
        )

    def _apply_ocr_fallback_to_node(
        self,
        node: BundleNode,
        document_text: Optional[str],
        markdown_text: str,
        fallback_type: str = "ocr_fallback",
    ) -> None:
        """
        Apply OCR fallback text to a node if it contains more content than markdown extraction.

        Args:
            node: The BundleNode to update
            document_text: OCR-extracted text from the document
            markdown_text: Text extracted via markdown rendering
            fallback_type: Type of fallback for metadata tracking
        """
        text_length = len(markdown_text.strip())

        if document_text and len(document_text.strip()) > text_length:
            # OCR found more text, use it
            node.markdown = document_text
            node.metadata[f"{fallback_type}_used"] = True
            node.metadata["ocr_word_count"] = len(document_text.split())
        else:
            # OCR didn't find more text, use markdown result
            node.markdown = markdown_text
            node.metadata[f"{fallback_type}_attempted"] = True
            if document_text:
                node.metadata["ocr_word_count"] = len(document_text.split())

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

            # Special case: markitdown renderer for simple files without attachments
            # For emails and PDFs, we need native parser first:
            # - Emails: Extract structure (attachments)
            # - PDFs: Detect if scanned and apply OCR fallback
            # Then we'll re-render with markitdown for clean content
            is_email = path.suffix.lower() in {".eml", ".msg"}
            is_pdf = path.suffix.lower() == ".pdf"
            needs_structure_extraction = is_email or is_pdf

            if options.renderer == "markitdown" and not needs_structure_extraction:
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

            # Smart rendering: use markitdown for content if requested
            # IMPORTANT: Render attachments BEFORE stripping binary payloads
            if options.renderer == "markitdown" and self._markitdown.available:
                rendered_root = self._render_with_smart_strategy(document, root_node, path, options)
            else:
                rendered_root = self._renderer.render(document, root_node, options)

            # Strip binary payloads after rendering is complete
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
            # NOTE: Don't strip binary here - let final _strip_binary_payloads() handle it
            # after rendering is complete

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

    def _render_with_smart_strategy(
        self,
        document: ExtractedDocument,
        root_node: BundleNode,
        path: Path,
        options: ParseOptions,
    ) -> BundleNode:
        """
        Smart rendering strategy: use MarkItDown for documents, native+OCR for images.

        For emails:
        - Body → MarkItDown (clean continuous narrative)
        - Document attachments (PDF, DOCX, XLSX) → MarkItDown (clean tables)
        - Image attachments (PNG, JPG) → native parser with OCR (text extraction)

        For PDFs:
        - Try MarkItDown first
        - If result is too short, assume scanned and fallback to native OCR
        """
        # Render main document content with MarkItDown
        try:
            main_markdown = self._markitdown.render_path(path)

            # For PDFs, check if MarkItDown result is suspiciously short (scanned PDF)
            is_pdf = path.suffix.lower() == ".pdf"

            if is_pdf and self._is_likely_scanned_pdf(main_markdown):
                # Likely a scanned PDF, apply OCR fallback
                self._apply_ocr_fallback_to_node(
                    root_node, document.text, main_markdown, fallback_type="ocr_fallback"
                )
            else:
                # Normal case: use MarkItDown result
                root_node.markdown = main_markdown

        except Exception:
            # Fallback to native renderer if MarkItDown fails
            root_node = self._renderer.render(document, root_node, options)
            return root_node

        # Add attachments as children (same as native renderer does)
        root_node.children = []
        if document.attachments:
            self._attach_children(root_node, document.attachments)

            # Process each attachment with smart rendering
            for att_node in root_node.children:
                self._render_attachment_smart(att_node, options)

        return root_node

    def _attach_children(self, parent: BundleNode, children):
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

    def _render_attachment_smart(self, node: BundleNode, options: ParseOptions) -> None:
        """
        Render attachment with smart strategy based on file type.

        Images → native parser + OCR for text extraction
        Documents → MarkItDown for clean tables and formatting
        """
        if not node.binary:
            # No binary data, skip rendering
            return

        is_image = self._is_image(node.name)

        if is_image:
            # Images: use native parser with OCR to extract text
            node.markdown = self._render_image_with_ocr(node, options)
        else:
            # Documents: use MarkItDown for clean markdown
            node.markdown = self._render_document_with_markitdown(node, options)

        # Recursively process children
        for child in node.children:
            self._render_attachment_smart(child, options)

    def _is_image(self, filename: str) -> bool:
        """Check if file is an image requiring OCR."""
        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
        return Path(filename).suffix.lower() in image_exts

    def _render_image_with_ocr(self, node: BundleNode, options: ParseOptions) -> str:
        """
        Render image with OCR text extraction using ImageParser.

        Returns markdown with extracted text or description.
        """
        if not node.binary:
            return (
                f"![{node.name}]({node.location or node.name})\n\n*Image attachment: {node.name}*"
            )

        try:
            suffix = Path(node.name).suffix or ".png"

            with managed_temp_file(suffix=suffix) as tmp_path:
                # Write binary to temp file
                tmp_path.write_bytes(node.binary)

                # Use ImageParser with OCR enabled
                image_parser = self._factory.get_parser("image")

                # Create options with OCR enabled by default for images
                ocr_options = ParseOptions(
                    ocr_enabled=True,
                    handwriting_enabled=options.handwriting_enabled,
                    ocr_language=options.ocr_language,
                    ocr_timeout=options.ocr_timeout,
                    extract_metadata=False,
                )

                document = image_parser.parse(tmp_path, ocr_options)

                # Format markdown with image reference and extracted text
                markdown_parts = [f"## Image: {node.name}\n"]

                if (
                    document.text
                    and document.text.strip()
                    and not document.text.startswith("[Image:")
                ):
                    # OCR extracted meaningful text
                    markdown_parts.append(f"**Extracted Text:**\n\n{document.text}")
                    node.metadata["ocr_enabled"] = True
                    node.metadata["ocr_word_count"] = len(document.text.split())
                else:
                    # No text extracted
                    markdown_parts.append(f"![{node.name}]({node.location or node.name})")
                    markdown_parts.append("\n*Image attachment (no text detected)*")
                    node.metadata["ocr_enabled"] = True
                    node.metadata["ocr_word_count"] = 0

                return "\n".join(markdown_parts)

        except Exception as e:
            # Fallback if OCR fails
            return f"![{node.name}]({node.location or node.name})\n\n*Image attachment (OCR failed: {str(e)})*"

    def _render_document_with_markitdown(self, node: BundleNode, options: ParseOptions) -> str:
        """
        Render document attachment with MarkItDown for clean tables.

        For PDFs: Smart fallback logic
        1. Try MarkItDown first (fast, works for digital PDFs)
        2. If result is too short (<100 chars or <20 words), assume scanned PDF
        3. Fall back to native parser with OCR enabled

        Saves bytes to temp file, processes with MarkItDown, returns markdown.
        """
        if not node.binary:
            return f"*Attachment: {node.name}*"

        try:
            suffix = Path(node.name).suffix or ".bin"

            with managed_temp_file(suffix=suffix) as tmp_path:
                # Write binary to temp file
                tmp_path.write_bytes(node.binary)

                # Render with MarkItDown
                markdown = self._markitdown.render_path(tmp_path)

                # Check if this is a PDF and if MarkItDown result is suspiciously short
                is_pdf = suffix.lower() == ".pdf"

                if is_pdf and self._is_likely_scanned_pdf(markdown):
                    # Likely a scanned PDF, fall back to native parser with OCR
                    try:
                        pdf_parser = self._factory.get_parser("pdf")

                        # Create options with OCR enabled for scanned PDFs (inherit from parent options)
                        ocr_options = ParseOptions(
                            ocr_enabled=True,
                            handwriting_enabled=options.handwriting_enabled,
                            ocr_language=options.ocr_language,
                            ocr_timeout=options.ocr_timeout,
                            extract_tables=True,
                            extract_metadata=False,
                        )

                        document = pdf_parser.parse(tmp_path, ocr_options)

                        # Use helper to apply OCR fallback
                        self._apply_ocr_fallback_to_node(
                            node, document.text, markdown, fallback_type="ocr_fallback"
                        )

                        # Return appropriate markdown based on what was used
                        if node.metadata.get("ocr_fallback_used"):
                            return f"## Attachment: {node.name} (OCR Processed)\n\n{document.text}"
                        else:
                            return f"## Attachment: {node.name}\n\n{markdown}"

                    except Exception as ocr_error:
                        # OCR fallback failed, use original MarkItDown result
                        node.metadata["ocr_fallback_failed"] = str(ocr_error)
                        return f"## Attachment: {node.name}\n\n{markdown}"

                # MarkItDown succeeded with good content
                return f"## Attachment: {node.name}\n\n{markdown}"

        except Exception as e:
            # Fallback if MarkItDown fails entirely
            return f"## Attachment: {node.name}\n\n*Content could not be rendered: {str(e)}*"
