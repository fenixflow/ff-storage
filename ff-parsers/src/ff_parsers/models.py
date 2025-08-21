"""
Data models for the ff-parsers package.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ExtractedText:
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
    confidence: float = 1.0

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")


@dataclass
class ExtractedTable:
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

    @property
    def row_count(self) -> int:
        """Get the number of data rows (excluding headers)."""
        return len(self.rows)

    @property
    def column_count(self) -> int:
        """Get the number of columns."""
        return len(self.headers)

    def to_dict(self) -> List[Dict[str, str]]:
        """Convert table to list of dictionaries with headers as keys."""
        return [dict(zip(self.headers, row)) for row in self.rows]


@dataclass
class ExtractedImage:
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


@dataclass
class DocumentMetadata:
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
    custom_properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailMetadata:
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
    to_addresses: List[str] = field(default_factory=list)
    cc_addresses: List[str] = field(default_factory=list)
    bcc_addresses: List[str] = field(default_factory=list)
    subject: Optional[str] = None
    date: Optional[datetime] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    attachments: List[str] = field(default_factory=list)


@dataclass
class ExtractedDocument:
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
    """

    text: str
    pages: List[ExtractedText] = field(default_factory=list)
    tables: List[ExtractedTable] = field(default_factory=list)
    images: List[ExtractedImage] = field(default_factory=list)
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    email_metadata: Optional[EmailMetadata] = None
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    extraction_timestamp: Optional[datetime] = None
    parser_version: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred during extraction."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if any warnings were generated during extraction."""
        return len(self.warnings) > 0

    @property
    def page_count(self) -> int:
        """Get the number of pages extracted."""
        return len(self.pages)

    @property
    def table_count(self) -> int:
        """Get the number of tables extracted."""
        return len(self.tables)

    @property
    def image_count(self) -> int:
        """Get the number of images found."""
        return len(self.images)

    def get_page_text(self, page_number: int) -> Optional[str]:
        """
        Get text for a specific page.

        Args:
            page_number: 1-indexed page number

        Returns:
            Text content of the page or None if page doesn't exist
        """
        for page in self.pages:
            if page.page == page_number:
                return page.content
        return None
