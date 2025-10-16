"""
Image parser implementation with OCR support using pytesseract.

Supports common image formats with text extraction via Optical Character Recognition (OCR).
Optionally supports handwriting recognition for insurance forms and handwritten documents.
"""

from pathlib import Path
from typing import Optional, Union

import pytesseract
from PIL import Image

from ..base import BaseParser, ParseOptions
from ..exceptions import CorruptedFileError, OCRError
from ..models import DocumentMetadata, ExtractedDocument, ExtractedImage, ExtractedText


class ImageParser(BaseParser):
    """
    Parser for image files with OCR capabilities.

    Extracts text from images using pytesseract (Tesseract OCR engine).
    Supports both standard text recognition and handwriting recognition.
    """

    def get_supported_extensions(self) -> list[str]:
        """Get supported image file extensions."""
        return [
            ".png",
            ".PNG",
            ".jpg",
            ".JPG",
            ".jpeg",
            ".JPEG",
            ".gif",
            ".GIF",
            ".bmp",
            ".BMP",
            ".tiff",
            ".tif",
            ".TIFF",
            ".TIF",
            ".webp",
            ".WEBP",
        ]

    def get_mime_types(self) -> list[str]:
        """Get supported MIME types."""
        return [
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/bmp",
            "image/tiff",
            "image/webp",
        ]

    def validate(self, file_path: Union[str, Path]) -> bool:
        """Validate that the file is a valid image."""
        try:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                return False

            # Try to open with PIL
            with Image.open(path) as img:
                # Verify the image can be loaded
                img.verify()
                return True
        except Exception:
            return False

    def extract_metadata(self, file_path: Union[str, Path]) -> DocumentMetadata:
        """Extract image metadata."""
        path = self._ensure_path(file_path)
        metadata = DocumentMetadata()

        try:
            with Image.open(path) as img:
                # Basic image properties
                metadata.mime_type = f"image/{img.format.lower()}" if img.format else None
                metadata.file_size = self._get_file_size(path)

                # Store image-specific metadata
                metadata.custom_properties["width"] = img.width
                metadata.custom_properties["height"] = img.height
                metadata.custom_properties["mode"] = img.mode
                metadata.custom_properties["format"] = img.format

                # Extract EXIF data if available
                if hasattr(img, "_getexif") and img._getexif():
                    exif_data = img._getexif()
                    if exif_data:
                        # Store relevant EXIF tags
                        for tag_id, value in exif_data.items():
                            try:
                                metadata.custom_properties[f"exif_{tag_id}"] = str(value)
                            except Exception:
                                continue

        except Exception as e:
            self._log_warning(f"Failed to extract metadata: {e}")

        return metadata

    def parse(
        self, file_path: Union[str, Path], options: Optional[ParseOptions] = None
    ) -> ExtractedDocument:
        """
        Parse image and extract text via OCR.

        Args:
            file_path: Path to the image file
            options: Parsing options (OCR enabled by default for images)

        Returns:
            ExtractedDocument with OCR-extracted text

        Raises:
            CorruptedFileError: If the image cannot be opened or processed
            OCRError: If OCR fails
        """
        path = self._ensure_path(file_path)
        options = options or self._get_default_options()

        # Create base document
        document = self._create_base_document(path)

        try:
            # Extract metadata
            if options.extract_metadata:
                document.metadata = self.extract_metadata(path)

            # Open image
            with Image.open(path) as img:
                # Store image metadata
                if options.extract_images:
                    image_metadata = ExtractedImage(
                        width=img.width,
                        height=img.height,
                        format=img.format,
                        caption=path.name,
                    )
                    document.images.append(image_metadata)

                # Perform OCR if enabled
                if options.ocr_enabled:
                    text = self._extract_text_with_ocr(img, options)

                    if text:
                        # Add extracted text
                        extracted_text = ExtractedText(
                            content=text,
                            page=1,
                            confidence=0.85,  # OCR has lower confidence than native text
                        )
                        document.pages.append(extracted_text)
                        document.text = text
                        document.metadata.word_count = len(text.split())
                    else:
                        # No text extracted
                        document.warnings.append(
                            "OCR enabled but no text was extracted from the image"
                        )
                        document.text = f"[Image: {path.name}]"
                else:
                    # OCR not enabled, just return image description
                    document.text = f"[Image: {path.name}]"
                    document.warnings.append(
                        "OCR not enabled - use ocr_enabled=True to extract text from images"
                    )

        except Image.UnidentifiedImageError as e:
            raise CorruptedFileError(
                f"Cannot identify image file: {str(e)}", partial_result=document
            )
        except Exception as e:
            raise CorruptedFileError(f"Failed to parse image: {str(e)}", partial_result=document)

        return document

    def _extract_text_with_ocr(self, img: Image.Image, options: ParseOptions) -> Optional[str]:
        """
        Extract text from an image using OCR.

        Args:
            img: PIL Image object
            options: Parsing options with OCR configuration

        Returns:
            Extracted text or None if no text found

        Raises:
            OCRError: If OCR processing fails
        """
        try:
            # Convert to RGB if necessary (tesseract works best with RGB)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Determine tesseract config based on options
            config = ""

            if options.handwriting_enabled:
                # Use handwriting recognition model (requires trained data)
                # Note: This requires additional tessdata files for handwriting
                self._log_info("Using handwriting recognition mode")
                # PSM 6 = Assume a single uniform block of text
                # OEM 1 = Neural nets LSTM engine only (best for handwriting)
                config = "--oem 1 --psm 6"
            else:
                # Standard OCR mode
                # PSM 3 = Fully automatic page segmentation (default)
                config = "--psm 3"

            # Perform OCR
            text = pytesseract.image_to_string(
                img,
                lang=options.ocr_language,
                timeout=options.ocr_timeout,
                config=config,
            )

            # Clean up the text
            if text:
                text = text.strip()
                if text:
                    self._log_info(f"OCR extracted {len(text)} characters")
                    return text

            return None

        except pytesseract.TesseractError as e:
            raise OCRError(f"Tesseract OCR failed: {str(e)}")
        except Exception as e:
            raise OCRError(f"OCR processing failed: {str(e)}")
