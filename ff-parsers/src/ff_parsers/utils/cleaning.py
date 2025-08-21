"""
Text cleaning utilities for ff-parsers.
"""

import re
import unicodedata
from typing import Optional


def remove_control_characters(text: str) -> str:
    """
    Remove control characters from text, keeping only printable characters.

    Args:
        text: Input text

    Returns:
        Text with control characters removed
    """
    # Remove all control characters except newline, tab, and carriage return
    return "".join(
        char for char in text if char in "\n\r\t" or not unicodedata.category(char).startswith("C")
    )


def normalize_whitespace(text: str, preserve_paragraphs: bool = True) -> str:
    """
    Normalize whitespace in text.

    Args:
        text: Input text
        preserve_paragraphs: If True, preserve paragraph breaks (double newlines)

    Returns:
        Text with normalized whitespace
    """
    if preserve_paragraphs:
        # Split by double newlines to preserve paragraphs
        paragraphs = text.split("\n\n")
        # Normalize whitespace within each paragraph
        normalized_paragraphs = []
        for para in paragraphs:
            # Replace multiple spaces/tabs with single space
            para = re.sub(r"[ \t]+", " ", para)
            # Replace multiple newlines with single newline
            para = re.sub(r"\n+", " ", para)
            # Strip leading/trailing whitespace
            para = para.strip()
            if para:
                normalized_paragraphs.append(para)
        return "\n\n".join(normalized_paragraphs)
    else:
        # Replace all whitespace with single spaces
        text = re.sub(r"\s+", " ", text)
        return text.strip()


def remove_excessive_newlines(text: str, max_consecutive: int = 2) -> str:
    """
    Remove excessive consecutive newlines.

    Args:
        text: Input text
        max_consecutive: Maximum number of consecutive newlines to allow

    Returns:
        Text with excessive newlines removed
    """
    pattern = r"\n{" + str(max_consecutive + 1) + ",}"
    replacement = "\n" * max_consecutive
    return re.sub(pattern, replacement, text)


def clean_text(
    text: str,
    remove_control: bool = True,
    normalize_spaces: bool = True,
    preserve_paragraphs: bool = True,
    max_newlines: Optional[int] = 2,
) -> str:
    """
    Clean text by removing unwanted characters and normalizing whitespace.

    Args:
        text: Input text to clean
        remove_control: Whether to remove control characters
        normalize_spaces: Whether to normalize whitespace
        preserve_paragraphs: Whether to preserve paragraph structure
        max_newlines: Maximum consecutive newlines (None = no limit)

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove control characters if requested
    if remove_control:
        text = remove_control_characters(text)

    # Normalize whitespace if requested
    if normalize_spaces:
        text = normalize_whitespace(text, preserve_paragraphs)

    # Remove excessive newlines if specified
    if max_newlines is not None:
        text = remove_excessive_newlines(text, max_newlines)

    return text.strip()


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length, adding suffix if truncated.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    if max_length <= len(suffix):
        return text[:max_length]

    return text[: max_length - len(suffix)] + suffix


def remove_extra_spaces_in_table(table_data: list[list[str]]) -> list[list[str]]:
    """
    Clean extra spaces from table cells.

    Args:
        table_data: Table data as list of rows

    Returns:
        Cleaned table data
    """
    cleaned_table = []
    for row in table_data:
        cleaned_row = [cell.strip() if isinstance(cell, str) else str(cell).strip() for cell in row]
        cleaned_table.append(cleaned_row)
    return cleaned_table
