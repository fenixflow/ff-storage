"""
Custom exceptions for the ff-parsers package.
"""


class ParserError(Exception):
    """Base exception for all parser-related errors."""

    pass


class UnsupportedFormatError(ParserError):
    """Raised when trying to parse an unsupported file format."""

    def __init__(self, file_format: str, supported_formats: list = None):
        self.file_format = file_format
        self.supported_formats = supported_formats or []

        if supported_formats:
            message = f"Unsupported format: {file_format}. Supported formats: {', '.join(supported_formats)}"
        else:
            message = f"Unsupported format: {file_format}"

        super().__init__(message)


class ExtractionError(ParserError):
    """Raised when content extraction fails."""

    def __init__(self, message: str, page: int = None, partial_result=None):
        self.page = page
        self.partial_result = partial_result

        if page:
            message = f"Extraction error on page {page}: {message}"

        super().__init__(message)


class FileNotFoundError(ParserError):
    """Raised when the specified file cannot be found."""

    pass


class CorruptedFileError(ParserError):
    """Raised when the file appears to be corrupted or unreadable."""

    def __init__(self, message: str, partial_result=None):
        self.partial_result = partial_result
        super().__init__(message)


class OCRError(ExtractionError):
    """Raised when OCR processing fails."""

    def __init__(self, message: str, page: int = None):
        super().__init__(f"OCR failed: {message}", page=page)


class PasswordProtectedError(ParserError):
    """Raised when trying to parse a password-protected file."""

    def __init__(self, file_type: str = "document"):
        super().__init__(f"Cannot parse password-protected {file_type}")


class EncodingError(ParserError):
    """Raised when text encoding cannot be determined or decoded."""

    def __init__(self, encoding: str = None, message: str = None):
        self.encoding = encoding
        if encoding:
            msg = f"Failed to decode with encoding '{encoding}'"
        else:
            msg = "Failed to determine text encoding"

        if message:
            msg = f"{msg}: {message}"

        super().__init__(msg)
