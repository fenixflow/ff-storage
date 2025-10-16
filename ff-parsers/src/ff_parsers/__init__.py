"""
ff-parsers: Lightweight document parsing library for extracting content from various file formats.
"""

# Version is read from package metadata (pyproject.toml is the single source of truth)
try:
    from importlib.metadata import version

    __version__ = version("ff-parsers")
except Exception:
    __version__ = "0.0.0+unknown"

from .adapters.fenix_agents import FenixAgentsPipelineAdapter, ParsedDocumentAdapter
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
