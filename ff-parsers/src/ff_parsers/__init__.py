"""
ff-parsers: Lightweight document parsing library for extracting content from various file formats.
"""

__version__ = "1.0.0"

from .base import BaseParser, ParseOptions
from .exceptions import ExtractionError, ParserError, UnsupportedFormatError
from .factory import ParserFactory
from .models import (
    BundleNode,
    DocumentBundle,
    DocumentMetadata,
    ExtractedDocument,
    ExtractedImage,
    ExtractedTable,
    ExtractedText,
)
from .pipeline.ingest import DocumentIngestionPipeline
from .renderers.markdown import MarkdownRenderer
from .renderers.markitdown import MarkItDownFallback
from .adapters.fenix_agents import FenixAgentsPipelineAdapter, ParsedDocumentAdapter

__all__ = [
    "ParserFactory",
    "ExtractedDocument",
    "ExtractedTable",
    "ExtractedText",
    "DocumentMetadata",
    "ExtractedImage",
    "BundleNode",
    "DocumentBundle",
    "DocumentIngestionPipeline",
    "MarkdownRenderer",
    "MarkItDownFallback",
    "FenixAgentsPipelineAdapter",
    "ParsedDocumentAdapter",
    "BaseParser",
    "ParseOptions",
    "ParserError",
    "UnsupportedFormatError",
    "ExtractionError",
]
