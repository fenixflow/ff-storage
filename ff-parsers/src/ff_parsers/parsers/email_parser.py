"""
Email parser implementation for .eml and .msg files.
"""

from __future__ import annotations

import email
import mimetypes
import re
from email import policy
from email.message import Message
from html import unescape
from pathlib import Path
from typing import List, Optional, Tuple, Union

from ..base import BaseParser, ParseOptions
from ..exceptions import CorruptedFileError
from ..models import BundleNode, DocumentMetadata, EmailMetadata, ExtractedDocument, ExtractedText
from ..utils.attachments import compute_sha256, split_extension
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

            if path.suffix.lower() not in [".eml", ".msg"]:
                return False

            if path.suffix.lower() == ".eml":
                with open(path, "rb") as handle:
                    email.message_from_binary_file(handle, policy=policy.default)
                return True

            # MSG files require an additional dependency (e.g. extract-msg); for now we only
            # verify the file exists.
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
                with open(path, "rb") as handle:
                    msg = email.message_from_binary_file(handle, policy=policy.default)

                metadata.title = msg.get("Subject", "")
                metadata.author = msg.get("From", "")

                date_str = msg.get("Date")
                if date_str:
                    try:
                        metadata.created_date = email.utils.parsedate_to_datetime(date_str)
                    except (TypeError, ValueError):
                        pass

        except Exception as exc:
            self._log_warning(f"Failed to extract metadata: {exc}")

        return metadata

    def parse(
        self, file_path: Union[str, Path], options: Optional[ParseOptions] = None
    ) -> ExtractedDocument:
        """Parse email file and extract content."""
        path = self._ensure_path(file_path)
        options = options or self._get_default_options()

        document = self._create_base_document(path)

        try:
            if path.suffix.lower() == ".eml":
                self._parse_eml(path, document, options)
            else:
                document.errors.append("MSG file parsing not yet implemented")
                document.warnings.append("Please convert MSG to EML format for full parsing")

            if options.extract_metadata:
                document.metadata = self.extract_metadata(path)

            if document.text:
                document.metadata.word_count = len(document.text.split())

        except Exception as exc:
            raise CorruptedFileError(f"Failed to parse email: {exc}", partial_result=document)

        return document

    def _parse_eml(self, path: Path, document: ExtractedDocument, options: ParseOptions) -> None:
        """Parse an EML file into an ExtractedDocument."""
        with open(path, "rb") as handle:
            message = email.message_from_binary_file(handle, policy=policy.default)

        email_meta = self._extract_email_metadata(message)
        document.email_metadata = email_meta

        body_segments, attachments = self._collect_message_parts(
            message=message, options=options, depth=0
        )

        header_text = self._format_email_headers(email_meta)
        sections = [section for section in [header_text, *body_segments] if section]
        full_text = "\n\n".join(sections)
        document.text = full_text

        if full_text:
            document.pages.append(ExtractedText(content=full_text, confidence=1.0))

        document.attachments = attachments
        email_meta.attachments = [
            node.name for node in attachments if node.kind != "inline" or node.name
        ]
        document.metadata.custom_properties["email_header_text"] = header_text
        document.metadata.custom_properties["email_body_segments"] = body_segments

    def _collect_message_parts(
        self, *, message: Message, options: ParseOptions, depth: int
    ) -> Tuple[List[str], List[BundleNode]]:
        """
        Collect body segments and attachment nodes from a MIME message.

        Returns:
            Tuple containing ordered body segments and a list of top-level attachment nodes.
        """
        if message.is_multipart():
            body_segments: List[str] = []
            attachments: List[BundleNode] = []
            for part in message.iter_parts():
                part_body, part_attachments = self._collect_message_parts(
                    message=part, options=options, depth=depth + 1
                )
                body_segments.extend(part_body)
                attachments.extend(part_attachments)
            return body_segments, attachments

        content_type = message.get_content_type()
        disposition = message.get_content_disposition() or ""
        filename = message.get_filename()
        payload = message.get_payload(decode=True)

        # Nested message (.eml attached within another email)
        if content_type == "message/rfc822" and payload is not None:
            nested_msg = email.message_from_bytes(payload, policy=policy.default)
            nested_meta = self._extract_email_metadata(nested_msg)
            nested_header = self._format_email_headers(nested_meta)
            nested_body, nested_children = self._collect_message_parts(
                message=nested_msg, options=options, depth=depth + 1
            )
            nested_sections = [section for section in [nested_header, *nested_body] if section]
            nested_markdown = "\n\n".join(nested_sections)

            node = self._build_attachment_node(
                name=filename or "nested-email.eml",
                content_type=content_type,
                disposition=disposition,
                payload=payload,
                message=message,
                kind="attachment",
                depth=depth,
            )
            if nested_markdown:
                node.markdown = nested_markdown
            node.metadata.update(
                {
                    "subject": nested_meta.subject,
                    "from": nested_meta.from_address,
                }
            )
            for child in nested_children:
                node.add_child(child)
            return [], [node]

        # Textual parts contribute to the body content.
        if content_type == "text/plain":
            text = self._extract_text_part(message, options)
            return ([text] if text else []), []

        if content_type == "text/html":
            html_text = self._extract_html_part(message, options)
            return ([html_text] if html_text else []), []

        # Inline images and attachments.
        if payload is not None:
            kind = "inline" if disposition == "inline" else "attachment"
            node = self._build_attachment_node(
                name=filename,
                content_type=content_type,
                disposition=disposition,
                payload=payload,
                message=message,
                kind=kind,
                depth=depth,
            )
            return [], [node]

        self._log_debug(
            f"Skipped message part with content-type={content_type} disposition={disposition}"
        )
        return [], []

    def _build_attachment_node(
        self,
        *,
        name: Optional[str],
        content_type: str,
        disposition: str,
        payload: bytes,
        message: Message,
        kind: str,
        depth: int,
    ) -> BundleNode:
        """Create a BundleNode representing an attachment or inline asset."""
        resolved_name = self._resolve_attachment_name(name, content_type)
        sha256 = compute_sha256(payload)
        size_bytes = len(payload)
        _, ext = split_extension(resolved_name)
        file_type = ext or mimetypes.guess_extension(content_type) or ""

        node = BundleNode(
            name=resolved_name,
            file_type=file_type,
            mime_type=content_type,
            sha256=sha256,
            size_bytes=size_bytes,
            content_id=self._normalise_content_id(message.get("Content-ID")),
            disposition=disposition or None,
            is_inline=kind == "inline",
            kind=kind,
            binary=payload,
            metadata={
                "content_type": content_type,
                "depth": depth,
                "disposition": disposition or None,
                "headers": {key: value for (key, value) in message.items()},
            },
        )

        return node

    def _extract_text_part(self, part: Message, options: ParseOptions) -> Optional[str]:
        """Extract and clean text from a text/plain part."""
        try:
            text = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")

        if not text:
            return None

        if not options.preserve_whitespace:
            text = clean_text(text)
        return text

    def _extract_html_part(self, part: Message, options: ParseOptions) -> Optional[str]:
        """Convert HTML to plain text."""
        try:
            html = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            html = payload.decode(charset, errors="replace")

        if not html:
            return None

        text = self._html_to_text(html)
        if not options.preserve_whitespace:
            text = clean_text(text)
        return text

    def _extract_email_metadata(self, msg: Message) -> EmailMetadata:
        """Extract metadata from email message."""
        meta = EmailMetadata()

        meta.from_address = self._extract_email_address(msg.get("From", ""))
        meta.to_addresses = self._extract_email_addresses(msg.get("To", ""))
        meta.cc_addresses = self._extract_email_addresses(msg.get("Cc", ""))
        meta.bcc_addresses = self._extract_email_addresses(msg.get("Bcc", ""))
        meta.subject = msg.get("Subject", "")

        date_str = msg.get("Date")
        if date_str:
            try:
                meta.date = email.utils.parsedate_to_datetime(date_str)
            except (TypeError, ValueError):
                pass

        meta.message_id = msg.get("Message-ID", "")
        meta.in_reply_to = msg.get("In-Reply-To", "")

        return meta

    def _extract_email_address(self, header: str) -> str:
        """Extract email address from header."""
        if not header:
            return ""
        _, addr = email.utils.parseaddr(header)
        return addr or header

    def _extract_email_addresses(self, header: str) -> List[str]:
        """Extract multiple email addresses from header."""
        if not header:
            return []
        addresses = []
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
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"<p[^>]*>", "\n\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</p>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<li[^>]*>", "- ", html, flags=re.IGNORECASE)
        html = re.sub(r"</li>", "\n", html, flags=re.IGNORECASE)
        html = re_sub_tag_cleanup(html)
        text = unescape(html)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _normalise_content_id(self, content_id: Optional[str]) -> Optional[str]:
        """Normalise the content ID header value."""
        if not content_id:
            return None
        return content_id.strip("<>")

    def _resolve_attachment_name(self, name: Optional[str], content_type: str) -> str:
        """Determine a filename for the attachment, ensuring an extension is present."""
        guessed_ext = mimetypes.guess_extension(content_type) or ""

        if name:
            stem, ext = split_extension(name)
            if ext:
                return name
            if guessed_ext:
                return f"{stem}{guessed_ext}"
            return name

        subtype = content_type.split("/")[-1] if "/" in content_type else ""
        base = subtype or "attachment"
        if guessed_ext:
            return f"{base}{guessed_ext}"
        return base


def re_sub_tag_cleanup(html: str) -> str:
    """Strip generic HTML tags."""
    return re.sub(r"<[^>]+>", "", html)
