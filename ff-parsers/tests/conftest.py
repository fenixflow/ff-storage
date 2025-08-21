"""
Pytest configuration and fixtures for ff-parsers tests.
"""

import pytest
from pathlib import Path
import tempfile
import shutil


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