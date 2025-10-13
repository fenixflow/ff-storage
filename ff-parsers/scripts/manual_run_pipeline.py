"""
Manual testing helper for the ff-parsers ingestion pipeline.

Usage:
    python scripts/manual_run_pipeline.py /path/to/file1 [/path/to/file2 ...] \
        --out ./output --renderer auto --ocr
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from ff_parsers import DocumentIngestionPipeline, ParseOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manually exercise the ingestion pipeline.")
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more files to ingest.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Directory to place generated bundles (defaults to <file>_bundle next to each file).",
    )
    parser.add_argument(
        "--renderer",
        choices=["auto", "markdownit", "native", "markitdown"],
        default="auto",
        help="Renderer to apply.",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR support.",
    )
    parser.add_argument(
        "--handwriting",
        action="store_true",
        help="Enable handwriting detection (implies OCR).",
    )
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Keep attachment bytes in the returned bundle (useful for inspection).",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Do not write markdown/manifest files, just print a summary.",
    )
    return parser


def ensure_output_dir(base: Path, override: Path | None) -> Path:
    if override is not None:
        return override
    return base.parent / f"{base.stem}_bundle"


def write_outputs(bundle, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / f"{bundle.document.name}.md"
    manifest_path = directory / f"{bundle.document.name}_manifest.json"

    markdown_path.write_text(bundle.markdown, encoding="utf-8")
    manifest_path.write_text(json.dumps(bundle.to_manifest(), indent=2), encoding="utf-8")

    if bundle.attachments_dir:
        print(f"  attachments saved under: {bundle.attachments_dir}")
    print(f"  markdown: {markdown_path}")
    print(f"  manifest: {manifest_path}")


def print_summary(bundle) -> None:
    counts = bundle.document.metadata.get("counts", {}) or {}
    print(f"  markdown length: {len(bundle.markdown)} characters")
    print(f"  attachments: {counts.get('attachments', 0)}")
    print(f"  tables: {counts.get('tables', 0)}, images: {counts.get('images', 0)}")
    print(f"  manifest keys: {list(bundle.to_manifest().keys())}")


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    pipeline = DocumentIngestionPipeline()
    options = ParseOptions(
        renderer=args.renderer,
        ocr_enabled=args.ocr or args.handwriting,
        handwriting_enabled=args.handwriting,
        include_binary_payloads=args.include_binary,
    )

    override_dir = Path(args.out).expanduser().resolve() if args.out else None

    for file_arg in args.files:
        path = Path(file_arg).expanduser().resolve()
        if not path.exists():
            print(f"[skip] missing file: {path}")
            continue

        print(f"[ingest] {path}")
        bundle = pipeline.ingest(path, options, output_dir=override_dir)
        print_summary(bundle)

        if not args.summary_only:
            out_dir = ensure_output_dir(path, override_dir)
            write_outputs(bundle, out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
