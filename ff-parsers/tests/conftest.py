"""
Pytest configuration and fixtures for ff-parsers tests.
"""

import shutil
import tempfile
from email.message import EmailMessage
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_text_file(temp_dir):
    """Create a sample text file."""
    file_path = temp_dir / "sample.txt"
    content = """This is a sample text file.
It has multiple lines.
And some content for testing.

This is a second paragraph.
With more text content."""

    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_csv_file(temp_dir):
    """Create a sample CSV file."""
    file_path = temp_dir / "sample.csv"
    content = """Name,Age,City
John Doe,30,New York
Jane Smith,25,Los Angeles
Bob Johnson,35,Chicago"""

    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_markdown_file(temp_dir):
    """Create a sample Markdown file."""
    file_path = temp_dir / "sample.md"
    content = """# Sample Markdown

This is a **sample** markdown file.

## Section 1

- Item 1
- Item 2
- Item 3

## Section 2

Some more text here."""

    file_path.write_text(content)
    return file_path


@pytest.fixture
def empty_file(temp_dir):
    """Create an empty file."""
    file_path = temp_dir / "empty.txt"
    file_path.touch()
    return file_path


@pytest.fixture
def non_existent_file(temp_dir):
    """Return path to a non-existent file."""
    return temp_dir / "does_not_exist.txt"


@pytest.fixture
def sample_email_file(temp_dir):
    """Create a simple EML file with a text body and attachment."""
    boundary = "===============123456789=="
    content = (
        "From: sender@example.com\n"
        "To: recipient@example.com\n"
        "Subject: Test Email\n"
        "Date: Mon, 01 Jan 2024 10:00:00 +0000\n"
        "MIME-Version: 1.0\n"
        f'Content-Type: multipart/mixed; boundary="{boundary}"\n'
        "\n"
        f"--{boundary}\n"
        'Content-Type: text/plain; charset="utf-8"\n'
        "\n"
        "Hello, this is the email body.\n"
        "\n"
        f"--{boundary}\n"
        'Content-Type: text/plain; charset="utf-8"; name="note.txt"\n'
        'Content-Disposition: attachment; filename="note.txt"\n'
        "Content-Transfer-Encoding: base64\n"
        "\n"
        "SGVsbG8gYXR0YWNobWVudCE=\n"
        f"--{boundary}--\n"
    )
    file_path = temp_dir / "sample.eml"
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture
def make_email_file(temp_dir):
    """Factory for creating temporary EML files with configurable attachments."""

    def _make(
        *,
        subject: str = "Test Email",
        body: str = "Hello",
        attachments: list[dict] | None = None,
        filename: str = "generated.eml",
    ) -> Path:
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = subject
        msg.set_content(body)

        for attachment in attachments or []:
            data = attachment.get("data", b"")
            maintype = attachment.get("maintype", "application")
            subtype = attachment.get("subtype", "octet-stream")
            name = attachment.get("filename")
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)

        path = temp_dir / filename
        path.write_bytes(msg.as_bytes())
        return path

    return _make
