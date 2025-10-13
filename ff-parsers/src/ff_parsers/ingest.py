"""
CLI entry point for the ff-parsers document ingestion pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .base import ParseOptions
from .pipeline.ingest import DocumentIngestionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest documents into Markdown bundles.")
    parser.add_argument("file", help="Path to the file to ingest.")
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Directory for pipeline outputs (markdown, manifest, attachments).",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR for scanned documents.",
    )
    parser.add_argument(
        "--handwriting",
        action="store_true",
        help="Enable handwriting extraction (implies OCR).",
    )
    parser.add_argument(
        "--renderer",
        type=str,
        default="auto",
        choices=["auto", "markdownit", "native", "markitdown"],
        help="Preferred Markdown renderer.",
    )
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Retain attachment binary payloads in the returned bundle.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.exists():
        parser.error(f"File not found: {file_path}")

    output_dir = (
        Path(args.out).expanduser().resolve()
        if args.out
        else file_path.parent / f"{file_path.stem}_bundle"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    options = ParseOptions(
        ocr_enabled=args.ocr or args.handwriting,
        handwriting_enabled=args.handwriting,
        renderer=args.renderer,
        include_binary_payloads=args.include_binary,
        attachment_root=str(output_dir / "attachments"),
    )

    pipeline = DocumentIngestionPipeline()
    bundle = pipeline.ingest(
        file_path,
        options,
        output_dir=output_dir,
    )

    markdown_path = output_dir / f"{file_path.stem}.md"
    manifest_path = output_dir / f"{file_path.stem}_manifest.json"

    markdown_path.write_text(bundle.markdown, encoding="utf-8")
    manifest_path.write_text(json.dumps(bundle.to_manifest(), indent=2), encoding="utf-8")

    print(f"Markdown written to: {markdown_path}")
    if bundle.attachments_dir:
        print(f"Attachments stored in: {bundle.attachments_dir}")
    print(f"Manifest written to: {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
