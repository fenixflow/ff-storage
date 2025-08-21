"""
ff-parsers: Lightweight document parsing library for extracting content from various file formats.
"""

__version__ = "0.1.0"

from .factory import ParserFactory
from .models import ExtractedDocument, ExtractedTable, ExtractedText, DocumentMetadata
from .base import BaseParser, ParseOptions
from .exceptions import ParserError, UnsupportedFormatError, ExtractionError

__all__ = [
    "ParserFactory",
    "ExtractedDocument",
    "ExtractedTable",
    "ExtractedText",
    "DocumentMetadata",
    "BaseParser",
    "ParseOptions",
    "ParserError",
    "UnsupportedFormatError",
    "ExtractionError",
]
