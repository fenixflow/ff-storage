"""
Tests for data models.
"""

import pytest
from ff_parsers.models import (
    BundleNode,
    DocumentMetadata,
    EmailMetadata,
    ExtractedDocument,
    ExtractedTable,
    ExtractedText,
)


class TestExtractedText:
    """Test ExtractedText model."""

    def test_creation(self):
        """Test creating ExtractedText."""
        text = ExtractedText(content="Sample text", page=1, paragraph=2, confidence=0.95)

        assert text.content == "Sample text"
        assert text.page == 1
        assert text.paragraph == 2
        assert text.confidence == 0.95

    def test_confidence_validation(self):
        """Test confidence score validation."""
        with pytest.raises(ValueError):
            ExtractedText(content="Test", confidence=1.5)

        with pytest.raises(ValueError):
            ExtractedText(content="Test", confidence=-0.1)


class TestExtractedTable:
    """Test ExtractedTable model."""

    def test_creation(self):
        """Test creating ExtractedTable."""
        table = ExtractedTable(
            headers=["Name", "Age", "City"],
            rows=[["John", "30", "NYC"], ["Jane", "25", "LA"]],
            page=1,
            name="Table1",
        )

        assert table.headers == ["Name", "Age", "City"]
        assert len(table.rows) == 2
        assert table.row_count == 2
        assert table.column_count == 3

    def test_to_dict(self):
        """Test converting table to dictionary."""
        table = ExtractedTable(headers=["Name", "Age"], rows=[["John", "30"], ["Jane", "25"]])

        dict_rows = table.to_dict()
        assert len(dict_rows) == 2
        assert dict_rows[0] == {"Name": "John", "Age": "30"}
        assert dict_rows[1] == {"Name": "Jane", "Age": "25"}


class TestExtractedDocument:
    """Test ExtractedDocument model."""

    def test_creation(self):
        """Test creating ExtractedDocument."""
        doc = ExtractedDocument(
            text="Document content",
            pages=[ExtractedText(content="Page 1", page=1)],
            tables=[ExtractedTable(headers=["Col1"], rows=[["Val1"]])],
            metadata=DocumentMetadata(title="Test Doc"),
        )

        assert doc.text == "Document content"
        assert doc.page_count == 1
        assert doc.table_count == 1
        assert doc.metadata.title == "Test Doc"

    def test_error_warnings(self):
        """Test error and warning tracking."""
        doc = ExtractedDocument(text="")

        assert not doc.has_errors
        assert not doc.has_warnings

        doc.errors.append("Error 1")
        doc.warnings.append("Warning 1")

        assert doc.has_errors
        assert doc.has_warnings

    def test_get_page_text(self):
        """Test getting text for specific page."""
        doc = ExtractedDocument(
            text="Full text",
            pages=[
                ExtractedText(content="Page 1", page=1),
                ExtractedText(content="Page 2", page=2),
            ],
        )

        assert doc.get_page_text(1) == "Page 1"
        assert doc.get_page_text(2) == "Page 2"
        assert doc.get_page_text(3) is None

    def test_add_attachment(self):
        """Ensure attachments can be registered."""
        doc = ExtractedDocument(text="")
        node = BundleNode(name="report.pdf", file_type=".pdf")

        doc.add_attachment(node)

        assert len(doc.attachments) == 1
        assert doc.attachments[0].name == "report.pdf"


class TestDocumentMetadata:
    """Test DocumentMetadata model."""

    def test_creation(self):
        """Test creating DocumentMetadata."""
        metadata = DocumentMetadata(
            title="Test Document",
            author="John Doe",
            page_count=10,
            word_count=500,
            custom_properties={"key": "value"},
        )

        assert metadata.title == "Test Document"
        assert metadata.author == "John Doe"
        assert metadata.page_count == 10
        assert metadata.word_count == 500
        assert metadata.custom_properties["key"] == "value"


class TestEmailMetadata:
    """Test EmailMetadata model."""

    def test_creation(self):
        """Test creating EmailMetadata."""
        metadata = EmailMetadata(
            from_address="sender@example.com",
            to_addresses=["recipient@example.com"],
            subject="Test Email",
            attachments=["file.pdf"],
        )

        assert metadata.from_address == "sender@example.com"
        assert metadata.to_addresses == ["recipient@example.com"]
        assert metadata.subject == "Test Email"
        assert metadata.attachments == ["file.pdf"]
