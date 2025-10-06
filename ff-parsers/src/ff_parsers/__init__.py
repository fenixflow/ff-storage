"""
ff-parsers: Lightweight document parsing library for extracting content from various file formats.
"""

__version__ = "0.1.0"

from .base import BaseParser, ParseOptions
from .exceptions import ExtractionError, ParserError, UnsupportedFormatError
from .factory import ParserFactory
from .models import DocumentMetadata, ExtractedDocument, ExtractedTable, ExtractedText

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
