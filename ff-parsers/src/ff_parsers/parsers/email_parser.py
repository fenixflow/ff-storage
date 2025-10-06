"""
Email parser implementation for .eml and .msg files.
"""

import email
import re
from email import policy
from html import unescape
from pathlib import Path
from typing import List, Optional, Union

from ..base import BaseParser, ParseOptions
from ..exceptions import CorruptedFileError
from ..models import DocumentMetadata, EmailMetadata, ExtractedDocument, ExtractedText
from ..utils.cleaning import clean_text


class EmailParser(BaseParser):
    """Parser for email files (.eml, .msg)."""

    def get_supported_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".eml", ".msg", ".EML", ".MSG"]

    def get_mime_types(self) -> list[str]:
        """Get supported MIME types."""
        return ["message/rfc822", "application/vnd.ms-outlook"]

    def validate(self, file_path: Union[str, Path]) -> bool:
        """Validate that the file is a valid email."""
        try:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                return False

            # Check extension
            if path.suffix.lower() not in [".eml", ".msg"]:
                return False

            if path.suffix.lower() == ".eml":
                # Try to parse as email
                with open(path, "rb") as f:
                    email.message_from_binary_file(f, policy=policy.default)
                return True
            else:
                # MSG files require additional library (extract-msg)
                # For now, we'll just check if file exists
                return True

        except Exception:
            return False

    def extract_metadata(self, file_path: Union[str, Path]) -> DocumentMetadata:
        """Extract email metadata."""
        path = self._ensure_path(file_path)
        metadata = DocumentMetadata()

        try:
            metadata.file_size = self._get_file_size(path)
            metadata.mime_type = "message/rfc822"

            if path.suffix.lower() == ".eml":
                with open(path, "rb") as f:
                    msg = email.message_from_binary_file(f, policy=policy.default)

                    # Extract basic metadata
                    metadata.title = msg.get("Subject", "")
                    metadata.author = msg.get("From", "")

                    # Parse date
                    date_str = msg.get("Date")
                    if date_str:
                        try:
                            metadata.created_date = email.utils.parsedate_to_datetime(date_str)
                        except (TypeError, ValueError):
                            pass

        except Exception as e:
            self._log_warning(f"Failed to extract metadata: {e}")

        return metadata

    def parse(
        self, file_path: Union[str, Path], options: Optional[ParseOptions] = None
    ) -> ExtractedDocument:
        """Parse email file and extract content."""
        path = self._ensure_path(file_path)
        options = options or self._get_default_options()

        # Create base document
        document = self._create_base_document(path)

        try:
            if path.suffix.lower() == ".eml":
                self._parse_eml(path, document, options)
            else:
                # MSG parsing would require extract-msg library
                document.errors.append("MSG file parsing not yet implemented")
                document.warnings.append("Please convert MSG to EML format for full parsing")

            # Extract metadata
            if options.extract_metadata:
                document.metadata = self.extract_metadata(path)

            # Count words
            if document.text:
                document.metadata.word_count = len(document.text.split())

        except Exception as e:
            raise CorruptedFileError(f"Failed to parse email: {str(e)}", partial_result=document)

        return document

    def _parse_eml(self, path: Path, document: ExtractedDocument, options: ParseOptions):
        """Parse EML file."""
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        # Extract email metadata
        email_meta = self._extract_email_metadata(msg)
        document.email_metadata = email_meta

        # Extract body
        body_parts = []
        attachments = []

        # Process message parts
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            # Skip multipart containers
            if part.is_multipart():
                continue

            # Check if it's an attachment
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append(filename)
                continue

            # Extract body content
            if content_type == "text/plain":
                try:
                    body = part.get_content()
                    if body:
                        body_parts.append(("plain", body))
                except Exception as e:
                    self._log_warning(f"Failed to extract plain text body: {e}")

            elif content_type == "text/html":
                try:
                    html_body = part.get_content()
                    if html_body:
                        # Convert HTML to plain text
                        plain_text = self._html_to_text(html_body)
                        body_parts.append(("html", plain_text))
                except Exception as e:
                    self._log_warning(f"Failed to extract HTML body: {e}")

        # Update attachment list in metadata
        document.email_metadata.attachments = attachments

        # Combine body parts
        all_text = []

        # Add headers as text
        header_text = self._format_email_headers(email_meta)
        all_text.append(header_text)

        # Add body content
        for content_type, content in body_parts:
            if content:
                # Clean the text
                if not options.preserve_whitespace:
                    content = clean_text(content)
                all_text.append(content)

        # Create extracted text
        full_text = "\n\n".join(all_text)
        document.text = full_text

        if full_text:
            document.pages.append(ExtractedText(content=full_text, confidence=1.0))

    def _extract_email_metadata(self, msg) -> EmailMetadata:
        """Extract metadata from email message."""
        meta = EmailMetadata()

        # From address
        from_header = msg.get("From", "")
        meta.from_address = self._extract_email_address(from_header)

        # To addresses
        to_header = msg.get("To", "")
        meta.to_addresses = self._extract_email_addresses(to_header)

        # CC addresses
        cc_header = msg.get("Cc", "")
        meta.cc_addresses = self._extract_email_addresses(cc_header)

        # BCC addresses (rarely visible in received emails)
        bcc_header = msg.get("Bcc", "")
        meta.bcc_addresses = self._extract_email_addresses(bcc_header)

        # Subject
        meta.subject = msg.get("Subject", "")

        # Date
        date_str = msg.get("Date")
        if date_str:
            try:
                meta.date = email.utils.parsedate_to_datetime(date_str)
            except (TypeError, ValueError):
                pass

        # Message ID
        meta.message_id = msg.get("Message-ID", "")

        # In-Reply-To
        meta.in_reply_to = msg.get("In-Reply-To", "")

        return meta

    def _extract_email_address(self, header: str) -> str:
        """Extract email address from header."""
        if not header:
            return ""

        # Use email.utils to parse the address
        name, addr = email.utils.parseaddr(header)
        return addr if addr else header

    def _extract_email_addresses(self, header: str) -> List[str]:
        """Extract multiple email addresses from header."""
        if not header:
            return []

        addresses = []
        # Split by comma for multiple addresses
        for addr_str in header.split(","):
            addr = self._extract_email_address(addr_str.strip())
            if addr:
                addresses.append(addr)

        return addresses

    def _format_email_headers(self, meta: EmailMetadata) -> str:
        """Format email headers as text."""
        lines = []

        if meta.from_address:
            lines.append(f"From: {meta.from_address}")

        if meta.to_addresses:
            lines.append(f"To: {', '.join(meta.to_addresses)}")

        if meta.cc_addresses:
            lines.append(f"Cc: {', '.join(meta.cc_addresses)}")

        if meta.subject:
            lines.append(f"Subject: {meta.subject}")

        if meta.date:
            lines.append(f"Date: {meta.date.strftime('%Y-%m-%d %H:%M:%S')}")

        if meta.attachments:
            lines.append(f"Attachments: {', '.join(meta.attachments)}")

        return "\n".join(lines)

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Replace br tags with newlines
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)

        # Replace p tags with double newlines
        html = re.sub(r"<p[^>]*>", "\n\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</p>", "", html, flags=re.IGNORECASE)

        # Replace list items with bullets
        html = re.sub(r"<li[^>]*>", "• ", html, flags=re.IGNORECASE)
        html = re.sub(r"</li>", "\n", html, flags=re.IGNORECASE)

        # Remove all other HTML tags
        html = re.sub(r"<[^>]+>", "", html)

        # Unescape HTML entities
        text = unescape(html)

        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        return text.strip()
