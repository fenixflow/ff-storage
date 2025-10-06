"""
Tests for ParserFactory.
"""

import pytest
from ff_parsers import ParserFactory
from ff_parsers.exceptions import UnsupportedFormatError
from ff_parsers.parsers import ExcelParser, TextParser


class TestParserFactory:
    """Test ParserFactory functionality."""

    def test_factory_creation(self):
        """Test creating a parser factory."""
        factory = ParserFactory()
        assert factory is not None
        assert len(factory._parsers) > 0

    def test_get_parser_by_type(self):
        """Test getting parser by type name."""
        factory = ParserFactory()

        # Test valid parser types
        text_parser = factory.get_parser("text")
        assert isinstance(text_parser, TextParser)

        excel_parser = factory.get_parser("excel")
        assert isinstance(excel_parser, ExcelParser)

    def test_get_parser_invalid_type(self):
        """Test getting parser with invalid type."""
        factory = ParserFactory()

        with pytest.raises(UnsupportedFormatError):
            factory.get_parser("invalid_type")

    def test_get_parser_for_file_by_extension(self, sample_text_file):
        """Test getting parser for file by extension."""
        factory = ParserFactory()
        parser = factory.get_parser_for_file(sample_text_file)

        assert isinstance(parser, TextParser)

    def test_get_parser_for_csv(self, sample_csv_file):
        """Test getting parser for CSV file."""
        factory = ParserFactory()
        parser = factory.get_parser_for_file(sample_csv_file)

        assert isinstance(parser, ExcelParser)

    def test_can_parse(self, sample_text_file):
        """Test checking if file can be parsed."""
        factory = ParserFactory()

        assert factory.can_parse(sample_text_file) is True
        assert factory.can_parse("nonexistent.xyz") is False

    def test_get_supported_formats(self):
        """Test getting supported formats."""
        factory = ParserFactory()
        formats = factory.get_supported_formats()

        assert "extensions" in formats
        assert "mime_types" in formats
        assert "parsers" in formats

        assert ".txt" in formats["extensions"]
        assert ".pdf" in formats["extensions"]
        assert ".xlsx" in formats["extensions"]

        assert "text" in formats["parsers"]
        assert "pdf" in formats["parsers"]
        assert "excel" in formats["parsers"]

    def test_get_supported_extensions(self):
        """Test getting supported extensions."""
        factory = ParserFactory()
        extensions = factory.get_supported_extensions()

        assert isinstance(extensions, list)
        assert ".txt" in extensions
        assert ".pdf" in extensions
        assert ".docx" in extensions

    def test_list_parsers(self):
        """Test listing all parsers."""
        factory = ParserFactory()
        parsers = factory.list_parsers()

        assert "text" in parsers
        assert "pdf" in parsers
        assert "excel" in parsers
        assert "email" in parsers
        assert "word" in parsers

        # Check parser info structure
        text_info = parsers["text"]
        assert "class" in text_info
        assert "extensions" in text_info
        assert "mime_types" in text_info
        assert text_info["class"] == "TextParser"
