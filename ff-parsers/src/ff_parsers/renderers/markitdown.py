"""
Optional MarkItDown fallback integration.
"""

from __future__ import annotations

from pathlib import Path

try:
    from markitdown import MarkItDown  # type: ignore import-not-found
except ImportError:  # pragma: no cover
    MarkItDown = None  # type: ignore[assignment]


class MarkItDownFallback:
    """Wrapper around the optional markitdown package."""

    def __init__(self) -> None:
        self._client = MarkItDown() if MarkItDown is not None else None

    @property
    def available(self) -> bool:
        """Whether markitdown is importable."""
        return self._client is not None

    def render_path(self, path: Path) -> str:
        """Convert a file to Markdown using markitdown."""
        if self._client is None:
            raise RuntimeError(
                "markitdown is not installed. Install the 'markitdown' package to enable fallback."
            )

        result = self._client.convert(str(path))
        if isinstance(result, tuple):
            markdown, _ = result
        else:
            markdown = result

        if hasattr(markdown, "text"):
            return getattr(markdown, "text")

        return str(markdown)
