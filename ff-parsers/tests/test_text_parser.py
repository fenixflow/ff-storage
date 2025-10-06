"""
Tests for TextParser.
"""

import pytest
from ff_parsers.base import ParseOptions
from ff_parsers.exceptions import FileNotFoundError
from ff_parsers.parsers.text_parser import TextParser


class TestTextParser:
    """Test TextParser functionality."""

    def test_supported_extensions(self):
        """Test supported extensions."""
        parser = TextParser()
        extensions = parser.get_supported_extensions()

        assert ".txt" in extensions
        assert ".md" in extensions
        assert ".log" in extensions

    def test_validate_valid_file(self, sample_text_file):
        """Test validating a valid text file."""
        parser = TextParser()
        assert parser.validate(sample_text_file) is True

    def test_validate_invalid_file(self, non_existent_file):
        """Test validating non-existent file."""
        parser = TextParser()
        assert parser.validate(non_existent_file) is False

    def test_parse_text_file(self, sample_text_file):
        """Test parsing a text file."""
        parser = TextParser()
        result = parser.parse(sample_text_file)

        assert result.text is not None
        assert "sample text file" in result.text
        assert "second paragraph" in result.text
        assert len(result.pages) > 0
        assert result.metadata.file_size > 0

    def test_parse_markdown_file(self, sample_markdown_file):
        """Test parsing a markdown file."""
        parser = TextParser()
        result = parser.parse(sample_markdown_file)

        assert result.text is not None
        assert "Sample Markdown" in result.text
        assert "Section 1" in result.text
        assert result.metadata.custom_properties.get("format") == "markdown"

    def test_parse_empty_file(self, empty_file):
        """Test parsing an empty file."""
        parser = TextParser()
        result = parser.parse(empty_file)

        assert result.text == ""
        assert len(result.pages) == 0

    def test_parse_with_options(self, sample_text_file):
        """Test parsing with custom options."""
        parser = TextParser()
        options = ParseOptions(preserve_whitespace=True, extract_metadata=False)

        result = parser.parse(sample_text_file, options)
        assert result.text is not None

    def test_extract_metadata(self, sample_text_file):
        """Test metadata extraction."""
        parser = TextParser()
        metadata = parser.extract_metadata(sample_text_file)

        assert metadata.file_size > 0
        assert metadata.mime_type == "text/plain"
        assert metadata.custom_properties.get("encoding") is not None

    def test_parse_non_existent_file(self, non_existent_file):
        """Test parsing non-existent file raises error."""
        parser = TextParser()

        with pytest.raises(FileNotFoundError):
            parser.parse(non_existent_file)
