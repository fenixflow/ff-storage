"""
PDF parser implementation using pdfplumber.
"""

from pathlib import Path
from typing import Optional, Union, List
from datetime import datetime
import pdfplumber
import pytesseract

from ..base import BaseParser, ParseOptions
from ..models import (
    ExtractedDocument,
    ExtractedText,
    ExtractedTable,
    ExtractedImage,
    DocumentMetadata,
)
from ..exceptions import CorruptedFileError, OCRError
from ..utils.cleaning import clean_text, remove_extra_spaces_in_table


class PDFParser(BaseParser):
    """Parser for PDF documents using pdfplumber."""

    def get_supported_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".pdf", ".PDF"]

    def get_mime_types(self) -> list[str]:
        """Get supported MIME types."""
        return ["application/pdf", "application/x-pdf"]

    def validate(self, file_path: Union[str, Path]) -> bool:
        """Validate that the file is a valid PDF."""
        try:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                return False

            # Try to open with pdfplumber
            with pdfplumber.open(path) as pdf:
                # Check if we can access at least the first page
                if len(pdf.pages) > 0:
                    return True
            return False
        except Exception:
            return False

    def extract_metadata(self, file_path: Union[str, Path]) -> DocumentMetadata:
        """Extract PDF metadata."""
        path = self._ensure_path(file_path)
        metadata = DocumentMetadata()

        try:
            with pdfplumber.open(path) as pdf:
                # Get PDF metadata
                pdf_meta = pdf.metadata or {}

                metadata.title = pdf_meta.get("Title")
                metadata.author = pdf_meta.get("Author")
                metadata.subject = pdf_meta.get("Subject")
                metadata.page_count = len(pdf.pages)

                # Extract keywords
                keywords = pdf_meta.get("Keywords")
                if keywords:
                    metadata.keywords = [k.strip() for k in keywords.split(",")]

                # Extract dates
                created = pdf_meta.get("CreationDate")
                if created:
                    try:
                        metadata.created_date = datetime.fromisoformat(str(created))
                    except (ValueError, TypeError):
                        pass

                modified = pdf_meta.get("ModDate")
                if modified:
                    try:
                        metadata.modified_date = datetime.fromisoformat(str(modified))
                    except (ValueError, TypeError):
                        pass

                # Store additional metadata
                for key, value in pdf_meta.items():
                    if key not in [
                        "Title",
                        "Author",
                        "Subject",
                        "Keywords",
                        "CreationDate",
                        "ModDate",
                    ]:
                        metadata.custom_properties[key] = str(value)

                metadata.file_size = self._get_file_size(path)
                metadata.mime_type = "application/pdf"

        except Exception as e:
            self._log_warning(f"Failed to extract metadata: {e}")

        return metadata

    def parse(
        self, file_path: Union[str, Path], options: Optional[ParseOptions] = None
    ) -> ExtractedDocument:
        """Parse PDF document and extract content."""
        path = self._ensure_path(file_path)
        options = options or self._get_default_options()

        # Create base document
        document = self._create_base_document(path)

        try:
            with pdfplumber.open(path) as pdf:
                # Extract metadata
                if options.extract_metadata:
                    document.metadata = self.extract_metadata(path)

                # Process pages
                all_text = []
                page_numbers = options.page_numbers or range(1, len(pdf.pages) + 1)

                if options.max_pages:
                    page_numbers = list(page_numbers)[: options.max_pages]

                for page_num in page_numbers:
                    if page_num > len(pdf.pages):
                        continue

                    try:
                        page = pdf.pages[page_num - 1]

                        # Extract text from page
                        page_text = self._extract_page_text(page, page_num, options)
                        if page_text:
                            document.pages.append(page_text)
                            all_text.append(page_text.content)

                        # Extract tables from page
                        if options.extract_tables:
                            page_tables = self._extract_page_tables(page, page_num)
                            document.tables.extend(page_tables)

                        # Extract images metadata
                        if options.extract_images:
                            page_images = self._extract_page_images(page, page_num)
                            document.images.extend(page_images)

                    except Exception as e:
                        error_msg = f"Error processing page {page_num}: {str(e)}"
                        document.errors.append(error_msg)
                        self._log_error(error_msg)

                # Combine all text
                document.text = "\n\n".join(all_text)

                # Count words
                if document.text:
                    document.metadata.word_count = len(document.text.split())

        except Exception as e:
            raise CorruptedFileError(f"Failed to parse PDF: {str(e)}", partial_result=document)

        return document

    def _extract_page_text(
        self, page, page_num: int, options: ParseOptions
    ) -> Optional[ExtractedText]:
        """Extract text from a single PDF page."""
        try:
            # Try regular text extraction first
            text = page.extract_text()

            if not text and options.ocr_enabled:
                # Page might be scanned, try OCR
                self._log_info(f"Page {page_num} appears to be scanned, attempting OCR")
                text = self._ocr_page(page, options)
                confidence = 0.8  # OCR results have lower confidence
            else:
                confidence = 1.0

            if text:
                # Clean the text
                if not options.preserve_whitespace:
                    text = clean_text(text)

                return ExtractedText(content=text, page=page_num, confidence=confidence)

            return None

        except Exception as e:
            self._log_warning(f"Failed to extract text from page {page_num}: {e}")
            return None

    def _ocr_page(self, page, options: ParseOptions) -> Optional[str]:
        """Perform OCR on a PDF page."""
        try:
            # Convert page to image
            pil_image = page.to_image(resolution=300).original

            # Perform OCR
            text = pytesseract.image_to_string(
                pil_image, lang=options.ocr_language, timeout=options.ocr_timeout
            )

            return text if text.strip() else None

        except Exception as e:
            raise OCRError(f"OCR failed: {str(e)}")

    def _extract_page_tables(self, page, page_num: int) -> List[ExtractedTable]:
        """Extract tables from a PDF page."""
        tables = []

        try:
            # Extract tables using pdfplumber
            page_tables = page.extract_tables()

            for idx, table_data in enumerate(page_tables):
                if not table_data or len(table_data) < 2:
                    continue

                # Clean table data
                table_data = remove_extra_spaces_in_table(table_data)

                # First row as headers
                headers = table_data[0]
                rows = table_data[1:]

                # Skip empty tables
                if not headers or not rows:
                    continue

                table = ExtractedTable(
                    headers=headers, rows=rows, page=page_num, name=f"Table_{page_num}_{idx + 1}"
                )
                tables.append(table)

        except Exception as e:
            self._log_warning(f"Failed to extract tables from page {page_num}: {e}")

        return tables

    def _extract_page_images(self, page, page_num: int) -> List[ExtractedImage]:
        """Extract image metadata from a PDF page."""
        images = []

        try:
            # Get images from page
            if hasattr(page, "images"):
                for idx, img in enumerate(page.images):
                    try:
                        image = ExtractedImage(
                            page=page_num,
                            index=idx + 1,
                            width=img.get("width"),
                            height=img.get("height"),
                        )
                        images.append(image)
                    except Exception as e:
                        self._log_warning(
                            f"Failed to extract image {idx} from page {page_num}: {e}"
                        )

        except Exception as e:
            self._log_warning(f"Failed to extract images from page {page_num}: {e}")

        return images
