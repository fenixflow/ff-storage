"""
Factory for creating appropriate parsers based on file type.
"""

from pathlib import Path
from typing import Dict, Type, Union

from .base import BaseParser
from .exceptions import UnsupportedFormatError
from .parsers import DocxParser, EmailParser, ExcelParser, PDFParser, TextParser
from .utils.validation import detect_file_type, get_mime_type


class ParserFactory:
    """
    Factory class for creating appropriate parsers based on file type.

    This class maintains a registry of parsers and can automatically
    select the appropriate parser based on file extension, MIME type,
    or content inspection.
    """

    def __init__(self):
        """Initialize the parser factory with default parsers."""
        self._parsers: Dict[str, Type[BaseParser]] = {}
        self._mime_parsers: Dict[str, Type[BaseParser]] = {}
        self._extension_parsers: Dict[str, Type[BaseParser]] = {}

        # Register default parsers
        self._register_default_parsers()

    def _register_default_parsers(self):
        """Register the default set of parsers."""
        # Register each parser
        self.register_parser("pdf", PDFParser)
        self.register_parser("excel", ExcelParser)
        self.register_parser("email", EmailParser)
        self.register_parser("word", DocxParser)
        self.register_parser("text", TextParser)

    def register_parser(self, name: str, parser_class: Type[BaseParser]):
        """
        Register a parser with the factory.

        Args:
            name: Name identifier for the parser
            parser_class: Parser class to register
        """
        # Store by name
        self._parsers[name] = parser_class

        # Create instance to get supported extensions and MIME types
        parser = parser_class()

        # Register extensions
        for ext in parser.get_supported_extensions():
            self._extension_parsers[ext.lower()] = parser_class

        # Register MIME types
        for mime in parser.get_mime_types():
            self._mime_parsers[mime] = parser_class

    def get_parser(self, parser_type: str, logger=None) -> BaseParser:
        """
        Get a parser by type name.

        Args:
            parser_type: Type of parser ('pdf', 'excel', 'email', 'word', 'text')
            logger: Optional logger to pass to parser

        Returns:
            Parser instance

        Raises:
            UnsupportedFormatError: If parser type is not supported
        """
        parser_class = self._parsers.get(parser_type.lower())

        if not parser_class:
            raise UnsupportedFormatError(parser_type, list(self._parsers.keys()))

        return parser_class(logger=logger)

    def get_parser_for_file(self, file_path: Union[str, Path], logger=None) -> BaseParser:
        """
        Automatically detect and return appropriate parser for a file.

        Args:
            file_path: Path to the file
            logger: Optional logger to pass to parser

        Returns:
            Appropriate parser instance

        Raises:
            UnsupportedFormatError: If no suitable parser found
        """
        file_path = Path(file_path)

        # Try extension first
        extension = file_path.suffix.lower()
        if extension in self._extension_parsers:
            parser_class = self._extension_parsers[extension]
            return parser_class(logger=logger)

        # Try MIME type detection
        mime_type = get_mime_type(file_path)
        if mime_type and mime_type in self._mime_parsers:
            parser_class = self._mime_parsers[mime_type]
            return parser_class(logger=logger)

        # Try content-based detection
        file_type = detect_file_type(file_path)
        if file_type and file_type in self._parsers:
            return self.get_parser(file_type, logger=logger)

        # No suitable parser found
        raise UnsupportedFormatError(f"File: {file_path.name}", self.get_supported_formats())

    def get_parser_for_mime_type(self, mime_type: str, logger=None) -> BaseParser:
        """
        Get parser for a specific MIME type.

        Args:
            mime_type: MIME type string
            logger: Optional logger to pass to parser

        Returns:
            Parser instance

        Raises:
            UnsupportedFormatError: If MIME type is not supported
        """
        parser_class = self._mime_parsers.get(mime_type)

        if not parser_class:
            raise UnsupportedFormatError(f"MIME type: {mime_type}", list(self._mime_parsers.keys()))

        return parser_class(logger=logger)

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """
        Check if a file can be parsed by any registered parser.

        Args:
            file_path: Path to the file

        Returns:
            True if file can be parsed, False otherwise
        """
        try:
            parser = self.get_parser_for_file(file_path)
            return parser.validate(file_path)
        except UnsupportedFormatError:
            return False

    def get_supported_formats(self) -> Dict[str, list]:
        """
        Get all supported formats organized by category.

        Returns:
            Dictionary with 'extensions', 'mime_types', and 'parsers'
        """
        return {
            "extensions": sorted(list(self._extension_parsers.keys())),
            "mime_types": sorted(list(self._mime_parsers.keys())),
            "parsers": sorted(list(self._parsers.keys())),
        }

    def get_supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions."""
        return sorted(list(self._extension_parsers.keys()))

    def get_supported_mime_types(self) -> list[str]:
        """Get list of all supported MIME types."""
        return sorted(list(self._mime_parsers.keys()))

    def list_parsers(self) -> Dict[str, Dict]:
        """
        List all registered parsers with their capabilities.

        Returns:
            Dictionary mapping parser names to their capabilities
        """
        result = {}

        for name, parser_class in self._parsers.items():
            parser = parser_class()
            result[name] = {
                "class": parser_class.__name__,
                "extensions": parser.get_supported_extensions(),
                "mime_types": parser.get_mime_types(),
            }

        return result
