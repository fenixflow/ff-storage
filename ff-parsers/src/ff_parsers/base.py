"""
Base parser interface for all document parsers.
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .exceptions import FileNotFoundError, ParserError
from .models import DocumentMetadata, ExtractedDocument


@dataclass
class ParseOptions:
    """
    Configuration options for document parsing.

    Attributes:
        extract_tables: Whether to extract tables from the document
        extract_images: Whether to extract images from the document
        extract_metadata: Whether to extract document metadata
        ocr_enabled: Whether to use OCR for scanned pages/images
        handwriting_enabled: Whether to enable handwriting models (requires OCR)
        ocr_language: Language code for OCR (e.g., 'eng', 'fra', 'deu')
        ocr_timeout: Timeout in seconds for OCR operations
        include_formatting: Whether to preserve text formatting information
        page_numbers: Specific page numbers to extract (None = all pages)
        max_pages: Maximum number of pages to process
        encoding: Text encoding to use (None = auto-detect)
        preserve_whitespace: Whether to preserve original whitespace
        extract_links: Whether to extract hyperlinks
        renderer: Markdown renderer selection ('auto', 'markdownit', 'native', 'markitdown')
        attachment_root: Directory where attachments should be persisted
        include_binary_payloads: Whether to keep attachment bytes in memory
    """

    extract_tables: bool = True
    extract_images: bool = True
    extract_metadata: bool = True
    ocr_enabled: bool = False
    handwriting_enabled: bool = False
    ocr_language: str = "eng"
    ocr_timeout: int = 30
    include_formatting: bool = False
    page_numbers: Optional[list[int]] = None
    max_pages: Optional[int] = None
    encoding: Optional[str] = None
    preserve_whitespace: bool = False
    extract_links: bool = False
    renderer: str = "auto"
    attachment_root: Optional[str] = None
    include_binary_payloads: bool = False


class BaseParser(ABC):
    """
    Abstract base class for all document parsers.

    This class defines the interface that all parsers must implement.
    """

    def __init__(self, logger=None):
        """
        Initialize the parser.

        Args:
            logger: Optional logger instance for debugging
        """
        self.logger = logger
        self.version = "0.1.0"

    @abstractmethod
    def parse(
        self, file_path: Union[str, Path], options: Optional[ParseOptions] = None
    ) -> ExtractedDocument:
        """
        Parse a document and extract its content.

        Args:
            file_path: Path to the document file
            options: Parsing options (uses defaults if None)

        Returns:
            ExtractedDocument containing all extracted content

        Raises:
            FileNotFoundError: If the file doesn't exist
            ParserError: If parsing fails
        """
        pass

    @abstractmethod
    def extract_metadata(self, file_path: Union[str, Path]) -> DocumentMetadata:
        """
        Extract only metadata from a document without parsing content.

        This method should be fast and extract only metadata without
        processing the full document content.

        Args:
            file_path: Path to the document file

        Returns:
            DocumentMetadata object

        Raises:
            FileNotFoundError: If the file doesn't exist
            ParserError: If metadata extraction fails
        """
        pass

    @abstractmethod
    def validate(self, file_path: Union[str, Path]) -> bool:
        """
        Validate that a file can be parsed by this parser.

        Args:
            file_path: Path to the document file

        Returns:
            True if the file can be parsed, False otherwise
        """
        pass

    @abstractmethod
    def get_supported_extensions(self) -> list[str]:
        """
        Get list of file extensions supported by this parser.

        Returns:
            List of supported extensions (e.g., ['.pdf', '.PDF'])
        """
        pass

    @abstractmethod
    def get_mime_types(self) -> list[str]:
        """
        Get list of MIME types supported by this parser.

        Returns:
            List of supported MIME types (e.g., ['application/pdf'])
        """
        pass

    def compute_file_hash(self, file_path: Union[str, Path]) -> str:
        """
        Compute SHA-256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hexadecimal string of the SHA-256 hash

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def _ensure_path(self, file_path: Union[str, Path]) -> Path:
        """
        Convert string path to Path object and verify it exists.

        Args:
            file_path: File path as string or Path

        Returns:
            Path object

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not path.is_file():
            raise ParserError(f"Path is not a file: {path}")

        return path

    def _get_file_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        return file_path.stat().st_size

    def _get_default_options(self) -> ParseOptions:
        """Get default parsing options."""
        return ParseOptions()

    def _log_debug(self, message: str):
        """Log debug message if logger is available."""
        if self.logger:
            self.logger.debug(message)

    def _log_info(self, message: str):
        """Log info message if logger is available."""
        if self.logger:
            self.logger.info(message)

    def _log_warning(self, message: str):
        """Log warning message if logger is available."""
        if self.logger:
            self.logger.warning(message)

    def _log_error(self, message: str):
        """Log error message if logger is available."""
        if self.logger:
            self.logger.error(message)

    def _create_base_document(self, file_path: Path) -> ExtractedDocument:
        """
        Create a base ExtractedDocument with common fields filled.

        Args:
            file_path: Path to the document

        Returns:
            ExtractedDocument with basic fields populated
        """
        return ExtractedDocument(
            text="",
            file_path=str(file_path),
            file_hash=self.compute_file_hash(file_path),
            extraction_timestamp=datetime.now(),
            parser_version=self.version,
            metadata=DocumentMetadata(file_size=self._get_file_size(file_path)),
        )
