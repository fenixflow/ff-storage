"""Tests for the document ingestion pipeline."""

from ff_parsers.base import ParseOptions
from ff_parsers.pipeline.ingest import DocumentIngestionPipeline


class _StubMarkItDown:
    available = True

    def render_path(self, path):
        return "# fallback"


def test_pipeline_ingests_text_document(sample_text_file, tmp_path):
    pipeline = DocumentIngestionPipeline()
    output_dir = tmp_path / "bundle"

    bundle = pipeline.ingest(
        sample_text_file,
        ParseOptions(),
        output_dir=output_dir,
    )

    assert bundle.document.name == sample_text_file.name
    assert bundle.markdown
    assert bundle.document.metadata["metadata"]["file_size"] > 0
    assert bundle.attachments_dir is None
    assert bundle.document.children == []


def test_pipeline_markitdown_fallback(sample_text_file, monkeypatch):
    pipeline = DocumentIngestionPipeline()
    pipeline._markitdown = _StubMarkItDown()
    monkeypatch.setattr(pipeline, "_hash_file", lambda path: "hash")

    bundle = pipeline.ingest(sample_text_file, ParseOptions(renderer="markitdown"))

    assert bundle.document.markdown == "# fallback"
    assert bundle.document.sha256 == "hash"
    assert bundle.attachments_dir is None


def test_pipeline_handles_attachment_metadata(make_email_file, tmp_path):
    eml_path = make_email_file(
        attachments=[
            {
                "data": b"",
                "maintype": "text",
                "subtype": "plain",
                "filename": "empty.txt",
            },
            {
                "data": b"\x89PNG",
                "maintype": "image",
                "subtype": "png",
                "filename": None,
            },
        ],
        filename="attachments.eml",
    )

    pipeline = DocumentIngestionPipeline()
    bundle = pipeline.ingest(eml_path, ParseOptions(), output_dir=tmp_path)

    root = bundle.document
    assert bundle.attachments_dir is not None
    assert len(root.children) == 2

    for child in root.children:
        assert child.parent_id == root.node_id
        assert child.depth == 1

    zero_child = next(node for node in root.children if node.size_bytes == 0)
    assert zero_child.location.endswith(".txt")

    png_child = next(node for node in root.children if node.mime_type == "image/png")
    assert png_child.location.endswith(".png")

    manifest = bundle.to_manifest()
    assert len(manifest["document"]["sub_files"]) == 2
