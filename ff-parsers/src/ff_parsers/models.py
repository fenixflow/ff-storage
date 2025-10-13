"""
Core Pydantic models used by ff-parsers.

These models describe the extracted document payloads as well as the bundle
structure returned by the ingestion pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class FFBaseModel(BaseModel):
    """Base Pydantic configuration shared by all ff-parsers models."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        populate_by_name=True,
        extra="ignore",
    )


class ExtractedText(FFBaseModel):
    """
    Represents extracted text with location information.

    Attributes:
        content: The extracted text content
        page: Page number (1-indexed) for PDFs and documents
        paragraph: Paragraph number within the page
        line: Line number for text files
        sheet: Sheet name for Excel files
        confidence: Confidence score (0.0-1.0) for OCR or uncertain extractions
    """

    content: str
    page: Optional[int] = None
    paragraph: Optional[int] = None
    line: Optional[int] = None
    sheet: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        if value is None or value == "":
            raise ValueError("ExtractedText.content must be a non-empty string")
        return value


class ExtractedTable(FFBaseModel):
    """
    Represents an extracted table with its data and location.

    Attributes:
        headers: List of column headers
        rows: List of rows, where each row is a list of cell values
        page: Page number where the table appears (for PDFs/documents)
        sheet: Sheet name where the table appears (for Excel)
        name: Optional table name or identifier
        cell_range: Cell range for Excel tables (e.g., "A1:D10")
    """

    headers: List[str]
    rows: List[List[str]]
    page: Optional[int] = None
    sheet: Optional[str] = None
    name: Optional[str] = None
    cell_range: Optional[str] = None

    @computed_field
    @property
    def row_count(self) -> int:
        """Number of data rows (excluding headers)."""
        return len(self.rows)

    @computed_field
    @property
    def column_count(self) -> int:
        """Number of columns."""
        return len(self.headers)

    def to_dict(self) -> List[Dict[str, str]]:
        """Convert table to list of dictionaries with headers as keys."""
        return [dict(zip(self.headers, row)) for row in self.rows]


class ExtractedImage(FFBaseModel):
    """
    Represents metadata about an extracted image.

    Attributes:
        image_data: Binary image data (optional, can be None to save memory)
        page: Page number where the image appears
        index: Index of the image within the page
        width: Image width in pixels
        height: Image height in pixels
        format: Image format (e.g., 'PNG', 'JPEG')
        caption: Optional caption or alt text
    """

    page: Optional[int] = None
    index: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None
    caption: Optional[str] = None
    image_data: Optional[bytes] = None


class DocumentMetadata(FFBaseModel):
    """
    Document-level metadata extracted from the file.

    Attributes:
        title: Document title
        author: Document author(s)
        subject: Document subject
        keywords: Document keywords
        created_date: Creation timestamp
        modified_date: Last modification timestamp
        page_count: Total number of pages
        word_count: Approximate word count
        language: Detected language code (e.g., 'en', 'es')
        file_size: File size in bytes
        mime_type: MIME type of the document
        custom_properties: Any additional metadata specific to the file type
    """

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[List[str]] = None
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    language: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    custom_properties: Dict[str, Any] = Field(default_factory=dict)


class EmailMetadata(FFBaseModel):
    """
    Email-specific metadata.

    Attributes:
        from_address: Sender email address
        to_addresses: List of recipient addresses
        cc_addresses: List of CC addresses
        bcc_addresses: List of BCC addresses
        subject: Email subject
        date: Email date
        message_id: Unique message identifier
        in_reply_to: Message ID this email replies to
        attachments: List of attachment filenames
    """

    from_address: Optional[str] = None
    to_addresses: List[str] = Field(default_factory=list)
    cc_addresses: List[str] = Field(default_factory=list)
    bcc_addresses: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    date: Optional[datetime] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)


class BundleNode(FFBaseModel):
    """
    Represents a node in the document bundle manifest.

    A node can be the primary document or a nested attachment. Each node can
    contain Markdown output, metadata, binary payloads, and child nodes.
    """

    node_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    file_type: Optional[str] = None
    location: Optional[str] = Field(
        default=None,
        description="Relative path to persisted asset within the bundle",
    )
    markdown: Optional[str] = None
    binary: Optional[bytes] = Field(
        default=None,
        description="Raw binary payload when the caller requests in-memory delivery.",
    )
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    source_path: Optional[str] = None
    content_id: Optional[str] = None
    disposition: Optional[str] = None
    is_inline: bool = False
    depth: int = 0
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    children: List["BundleNode"] = Field(default_factory=list)

    kind: str = Field(
        default="document",
        description="Semantic category for the node (document|attachment|inline|archive).",
    )

    def add_child(self, child: "BundleNode") -> "BundleNode":
        """Attach a child node and return it for fluent usage."""
        child.parent_id = self.node_id
        child.depth = self.depth + 1
        self.children.append(child)
        return child

    def iter_nodes(self) -> Iterator["BundleNode"]:
        """Depth-first iteration over the node and all descendants."""
        yield self
        for child in self.children:
            yield from child.iter_nodes()

    def to_manifest(self, include_binary: bool = False) -> Dict[str, Any]:
        """
        Convert the node (and its subtree) into a serialisable manifest.

        Args:
            include_binary: Whether to include binary payloads. Defaults to False.
        """
        payload: Dict[str, Any] = {
            "id": self.node_id,
            "name": self.name,
            "location": self.location,
            "file_type": self.file_type,
            "markdown": self.markdown,
            "mime_type": self.mime_type,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "source_path": self.source_path,
            "content_id": self.content_id,
            "disposition": self.disposition,
            "is_inline": self.is_inline,
            "kind": self.kind,
            "metadata": self.metadata,
            "sub_files": [
                child.to_manifest(include_binary=include_binary) for child in self.children
            ],
        }

        if include_binary and self.binary is not None:
            payload["binary"] = self.binary

        return payload


class DocumentBundle(FFBaseModel):
    """
    Result returned by the DocumentIngestionPipeline.

    Attributes:
        document: Root node representing the primary document.
        attachments_dir: Path where attachments were persisted (if any).
        created_at: Timestamp when the bundle was produced.
        source_path: Original source path when available.
        options: Normalised parse/renderer options used for ingestion.
    """

    document: BundleNode
    attachments_dir: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_path: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)

    def to_manifest(self, include_binary: bool = False) -> Dict[str, Any]:
        """Serialise the bundle into a nested manifest dictionary."""
        return {
            "created_at": self.created_at.isoformat(),
            "source_path": self.source_path,
            "attachments_dir": self.attachments_dir,
            "document": self.document.to_manifest(include_binary=include_binary),
        }

    @computed_field
    @property
    def markdown(self) -> str:
        """Primary document markdown (empty string when unavailable)."""
        return self.document.markdown or ""

    def iter_attachments(self) -> Iterable[BundleNode]:
        """Yield only attachment nodes (excluding the root document)."""
        for node in self.document.iter_nodes():
            if node is self.document:
                continue
            yield node


class ExtractedDocument(FFBaseModel):
    """
    Complete extracted document with all content and metadata.

    Attributes:
        text: Full extracted text as a single string
        pages: List of text extracted page by page (for documents)
        tables: List of extracted tables
        images: List of extracted image metadata
        metadata: Document metadata
        email_metadata: Email-specific metadata (if applicable)
        file_path: Original file path
        file_hash: SHA-256 hash of the original file
        extraction_timestamp: When the extraction was performed
        parser_version: Version of the parser used
        errors: List of non-fatal errors encountered during parsing
        warnings: List of warnings (e.g., "Some pages required OCR")
        attachments: Attachment nodes collected during parsing
    """

    text: str = ""
    pages: List[ExtractedText] = Field(default_factory=list)
    tables: List[ExtractedTable] = Field(default_factory=list)
    images: List[ExtractedImage] = Field(default_factory=list)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    email_metadata: Optional[EmailMetadata] = None
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    extraction_timestamp: Optional[datetime] = None
    parser_version: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    attachments: List[BundleNode] = Field(default_factory=list)

    @computed_field
    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred during extraction."""
        return bool(self.errors)

    @computed_field
    @property
    def has_warnings(self) -> bool:
        """Check if any warnings were generated during extraction."""
        return bool(self.warnings)

    @computed_field
    @property
    def page_count(self) -> int:
        """Number of pages extracted."""
        return len(self.pages)

    @computed_field
    @property
    def table_count(self) -> int:
        """Number of tables extracted."""
        return len(self.tables)

    @computed_field
    @property
    def image_count(self) -> int:
        """Number of images extracted."""
        return len(self.images)

    def add_attachment(self, node: BundleNode) -> BundleNode:
        """Register an attachment node on the document."""
        self.attachments.append(node)
        return node

    def get_page_text(self, page_number: int) -> Optional[str]:
        """Return the text content for a specific page when available."""
        for page in self.pages:
            if page.page == page_number:
                return page.content
        return None


# Rebuild forward references now that the classes are defined.
BundleNode.model_rebuild()
DocumentBundle.model_rebuild()
