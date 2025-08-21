"""
Plain text file parser implementation.
"""

from pathlib import Path
from typing import Optional, Union
from datetime import datetime
import chardet

from ..base import BaseParser, ParseOptions
from ..models import ExtractedDocument, ExtractedText, DocumentMetadata
from ..exceptions import ExtractionError
from ..utils.cleaning import clean_text


class TextParser(BaseParser):
    """Parser for plain text files."""

    def get_supported_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [
            ".txt",
            ".text",
            ".md",
            ".markdown",
            ".rst",
            ".log",
            ".TXT",
            ".TEXT",
            ".MD",
            ".MARKDOWN",
            ".RST",
            ".LOG",
        ]

    def get_mime_types(self) -> list[str]:
        """Get supported MIME types."""
        return ["text/plain", "text/markdown", "text/x-rst", "text/x-log", "application/x-log"]

    def validate(self, file_path: Union[str, Path]) -> bool:
        """Validate that the file is a valid text file."""
        try:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                return False

            # Try to detect encoding and read first few bytes
            with open(path, "rb") as f:
                raw_data = f.read(1024)
                if raw_data:
                    # Try to detect encoding
                    result = chardet.detect(raw_data)
                    if result["encoding"]:
                        return True

            return False

        except Exception:
            return False

    def extract_metadata(self, file_path: Union[str, Path]) -> DocumentMetadata:
        """Extract text file metadata."""
        path = self._ensure_path(file_path)
        metadata = DocumentMetadata()

        try:
            metadata.file_size = self._get_file_size(path)
            metadata.mime_type = "text/plain"

            # Get file stats
            stat = path.stat()
            metadata.created_date = datetime.fromtimestamp(stat.st_ctime)
            metadata.modified_date = datetime.fromtimestamp(stat.st_mtime)

            # Detect encoding
            encoding = self._detect_encoding(path)
            metadata.custom_properties["encoding"] = encoding

            # Quick line and word count
            try:
                with open(path, "r", encoding=encoding) as f:
                    lines = f.readlines()
                    metadata.custom_properties["line_count"] = len(lines)

                    # Estimate word count from first 100 lines
                    sample_lines = lines[:100]
                    sample_text = "".join(sample_lines)
                    words_in_sample = len(sample_text.split())

                    if len(lines) <= 100:
                        metadata.word_count = words_in_sample
                    else:
                        # Estimate total words
                        avg_words_per_line = words_in_sample / len(sample_lines)
                        metadata.word_count = int(avg_words_per_line * len(lines))
            except (IOError, OSError, UnicodeDecodeError):
                pass

            # Detect file type from extension
            if path.suffix.lower() in [".md", ".markdown"]:
                metadata.custom_properties["format"] = "markdown"
            elif path.suffix.lower() == ".rst":
                metadata.custom_properties["format"] = "restructuredtext"
            elif path.suffix.lower() == ".log":
                metadata.custom_properties["format"] = "log"
            else:
                metadata.custom_properties["format"] = "plain"

        except Exception as e:
            self._log_warning(f"Failed to extract metadata: {e}")

        return metadata

    def parse(
        self, file_path: Union[str, Path], options: Optional[ParseOptions] = None
    ) -> ExtractedDocument:
        """Parse text file and extract content."""
        path = self._ensure_path(file_path)
        options = options or self._get_default_options()

        # Create base document
        document = self._create_base_document(path)

        try:
            # Detect encoding if not specified
            encoding = options.encoding or self._detect_encoding(path)

            # Read file content
            try:
                with open(path, "r", encoding=encoding) as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try with fallback encoding
                self._log_warning(f"Failed with {encoding}, trying utf-8 with errors='ignore'")
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    document.warnings.append(
                        "Some characters may have been lost due to encoding issues"
                    )

            # Clean text if requested
            if not options.preserve_whitespace:
                content = clean_text(content)

            # Store full text
            document.text = content

            # Extract by lines if needed
            lines = content.splitlines()

            # Create pages based on lines (e.g., 50 lines per "page")
            lines_per_page = 50
            page_num = 1

            for i in range(0, len(lines), lines_per_page):
                page_lines = lines[i : i + lines_per_page]
                page_text = "\n".join(page_lines)

                if page_text.strip():
                    extracted = ExtractedText(
                        content=page_text,
                        page=page_num,
                        line=i + 1,  # Starting line number
                        confidence=1.0,
                    )
                    document.pages.append(extracted)

                page_num += 1

            # If no pages were created (empty file or very short), create one
            if not document.pages and content:
                extracted = ExtractedText(content=content, page=1, line=1, confidence=1.0)
                document.pages.append(extracted)

            # Extract metadata
            if options.extract_metadata:
                document.metadata = self.extract_metadata(path)

            # Update word count
            if document.text:
                document.metadata.word_count = len(document.text.split())

        except Exception as e:
            raise ExtractionError(f"Failed to parse text file: {str(e)}", partial_result=document)

        return document

    def _detect_encoding(self, path: Path) -> str:
        """Detect the encoding of a text file."""
        try:
            # Read a sample of the file
            with open(path, "rb") as f:
                raw_data = f.read(10000)  # Read first 10KB

            # Detect encoding
            result = chardet.detect(raw_data)
            encoding = result.get("encoding")
            confidence = result.get("confidence", 0)

            # Log detection result
            self._log_debug(f"Detected encoding: {encoding} (confidence: {confidence:.2f})")

            # If confidence is low or encoding is None, use UTF-8
            if not encoding or confidence < 0.7:
                self._log_warning("Low confidence encoding detection, defaulting to UTF-8")
                return "utf-8"

            # Map some common encoding aliases
            encoding_map = {
                "ascii": "utf-8",  # ASCII is subset of UTF-8
                "ISO-8859-1": "latin-1",
                "ISO-8859-2": "latin-2",
                "Windows-1252": "cp1252",
                "Windows-1251": "cp1251",
            }

            return encoding_map.get(encoding, encoding)

        except Exception as e:
            self._log_warning(f"Failed to detect encoding: {e}, defaulting to UTF-8")
            return "utf-8"
