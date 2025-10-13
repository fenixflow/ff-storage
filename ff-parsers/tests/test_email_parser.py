"""
Tests for the email parser focusing on attachment extraction.
"""

from ff_parsers.base import ParseOptions
from ff_parsers.parsers.email_parser import EmailParser


def test_email_parser_extracts_attachments(sample_email_file):
    parser = EmailParser()
    options = ParseOptions()

    document = parser.parse(sample_email_file, options)

    assert document.email_metadata is not None
    assert document.email_metadata.subject == "Test Email"
    assert "note.txt" in document.email_metadata.attachments
    assert document.attachments, "Expected attachment nodes to be present"

    attachment = document.attachments[0]
    assert attachment.name == "note.txt"
    assert attachment.binary == b"Hello attachment!"
    assert attachment.mime_type.startswith("text/")
    assert attachment.metadata["content_type"].startswith("text/plain")


def test_email_parser_keeps_zero_length_attachment(make_email_file):
    parser = EmailParser()
    path = make_email_file(
        attachments=[
            {
                "data": b"",
                "maintype": "text",
                "subtype": "plain",
                "filename": "empty.txt",
            }
        ]
    )

    document = parser.parse(path, ParseOptions())

    assert document.attachments, "Expected zero-byte attachment to be present"
    node = document.attachments[0]
    assert node.name == "empty.txt"
    assert node.size_bytes == 0
    assert node.binary == b""
    assert "empty.txt" in document.email_metadata.attachments


def test_email_parser_adds_extension_for_nameless_attachment(make_email_file):
    parser = EmailParser()
    path = make_email_file(
        attachments=[
            {
                "data": b"binary",
                "maintype": "image",
                "subtype": "png",
                "filename": None,
            }
        ]
    )

    document = parser.parse(path, ParseOptions())

    assert document.attachments, "Expected attachment to be present"
    node = document.attachments[0]
    assert node.file_type == ".png"
    assert node.name.endswith(".png")
