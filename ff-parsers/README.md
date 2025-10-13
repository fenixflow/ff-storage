# ff-parsers

A lightweight document parsing library for extracting content from various file formats with basic provenance tracking.

## Features

- **Markdown + Manifest Bundles**: Produce clean Markdown alongside a manifest describing attachments, hashes, and storage locations.
- **Attachment Awareness**: Recursively extract email attachments (including nested `.eml` files) and persist assets deterministically.
- **Configurable Pipeline**: Single entry point (`DocumentIngestionPipeline`) that handles parser selection, rendering, and persistence.
- **Multiple Format Support**: PDF, Excel (xlsx/xls/csv), Word (docx), Email (eml), and plain text files.
- **Structured Models**: Pydantic models for everything (documents, metadata, bundles) ready for JSON serialisation.
- **OCR & Handwriting Toggles**: Propagate OCR/handwriting preferences through parsers and renderers.
- **CLI & Adapter**: Run `python -m ff_parsers.ingest` for manual ingestion or use the fenix-agents adapter to stay API-compatible.
- **MarkItDown Fallback**: Optionally defer to the `markitdown` package when no native parser is available.

## Installation

```bash
# From GitLab Package Registry
uv pip install ff-parsers \
  --index-url https://<token_name>:<token>@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple

# From Git repository
pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-parsers

# Local development
pip install -e ./ff-parsers
```

### Optional Dependencies

For OCR support, install Tesseract:
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
```

## Quick Start

### Document Ingestion Pipeline

```python
from pathlib import Path

from ff_parsers import DocumentIngestionPipeline, ParseOptions

pipeline = DocumentIngestionPipeline()
bundle = pipeline.ingest(
    Path("reports/monthly.pdf"),
    ParseOptions(renderer="auto", ocr_enabled=True),
    output_dir=Path("output/monthly_report"),
)

print(bundle.markdown[:400])  # Clean Markdown ready for chunking
print(bundle.attachments_dir)  # Directory where assets were persisted

# Serialise manifest for storage or downstream processing
manifest = bundle.to_manifest()
```

Each ingestion returns a `DocumentBundle`:

- `document`: root `BundleNode` containing primary Markdown and metadata.
- `attachments_dir`: path where attachments were written (or `None` when no attachments).
- `options`: normalised options used for parsing/rendering.
- `iter_attachments()`: iterate through every attachment node in the tree.

See [`ff_parsers.models`](src/ff_parsers/models.py) for the full Pydantic model definitions.

### CLI Usage

```bash
python -m ff_parsers.ingest path/to/file.eml --out ./bundle --ocr --renderer auto
```

The CLI writes three things into `--out`:

- `<name>.md` – the rendered Markdown.
- `<name>_manifest.json` – serialisable manifest (document + attachments).
- `attachments/` – deterministic filenames for every extracted asset.

Use `--handwriting` to enable handwriting inference (implies OCR) and `--include-binary` to keep attachment bytes in the manifest payload.

> **Tip:** install the optional [`markitdown`](https://github.com/microsoft/markitdown) package to enable fallback rendering for formats that lack native parsers. Configure `ParseOptions(renderer="markitdown")` to force the fallback.

### Manual Testing Script

For ad-hoc validation outside the CLI, a helper script is provided:

```bash
python scripts/manual_run_pipeline.py /path/to/file1 /path/to/file2 --out ./bundles --renderer auto --ocr
```

It prints a compact summary for each file (markdown length, attachment counts) and, unless `--summary-only` is supplied, writes markdown, manifest, and attachments to the output directory.

### fenix-agents Adapter

The package includes a thin adapter that returns a `ParsedDocument`-compatible payload for fenix-agents:

```python
from ff_parsers import FenixAgentsPipelineAdapter, ParseOptions

adapter = FenixAgentsPipelineAdapter()
parsed = adapter.ingest("/path/to/file.eml", ParseOptions())

print(parsed.content)               # Markdown content
print(parsed.manifest["document"]) # Access manifest/attachments metadata
```

`ParsedDocumentAdapter` mirrors the fenix-agents `ParsedDocument` fields and adds `manifest` + `attachments_dir` for downstream ingestion.

### Using the Parser Factory Directly

```python
from ff_parsers import ParserFactory, ParseOptions

factory = ParserFactory()

parser = factory.get_parser_for_file("document.pdf")
result = parser.parse("document.pdf", ParseOptions(ocr_enabled=True))

print(result.text)  # Full text
print(f"Pages: {result.page_count}")
print(f"Tables: {result.table_count}")
print(f"Title: {result.metadata.title}")
print(f"Author: {result.metadata.author}")
```

### Parse Specific File Types

```python
from ff_parsers import ParserFactory, ParseOptions

factory = ParserFactory()

# PDF with OCR
pdf_parser = factory.get_parser("pdf")
options = ParseOptions(
    ocr_enabled=True,
    ocr_language="eng",
    extract_tables=True,
    extract_images=True
)
pdf_result = pdf_parser.parse("scanned_document.pdf", options)

# Excel file
excel_parser = factory.get_parser("excel")
excel_result = excel_parser.parse("data.xlsx")

# Access tables
for table in excel_result.tables:
    print(f"Table: {table.name}")
    print(f"Headers: {table.headers}")
    print(f"Rows: {table.row_count}")
    
    # Convert to dictionary format
    for row_dict in table.to_dict():
        print(row_dict)

# Email file
email_parser = factory.get_parser("email")
email_result = email_parser.parse("message.eml")

# Access email metadata
if email_result.email_metadata:
    print(f"From: {email_result.email_metadata.from_address}")
    print(f"To: {', '.join(email_result.email_metadata.to_addresses)}")
    print(f"Subject: {email_result.email_metadata.subject}")
    print(f"Attachments: {email_result.email_metadata.attachments}")
```

### Working with Extracted Content

```python
# Page-by-page access
for page in result.pages:
    print(f"Page {page.page}: {page.content[:100]}...")
    print(f"Confidence: {page.confidence}")  # Lower for OCR content

# Table data
for table in result.tables:
    # Access as list of lists
    for row in table.rows:
        print('\t'.join(row))
    
    # Or as list of dictionaries
    for row_dict in table.to_dict():
        for column, value in row_dict.items():
            print(f"{column}: {value}")

# Check for errors
if result.has_errors:
    print("Errors encountered:")
    for error in result.errors:
        print(f"  - {error}")

if result.has_warnings:
    print("Warnings:")
    for warning in result.warnings:
        print(f"  - {warning}")
```

### Parse Options

```python
from ff_parsers import ParseOptions

options = ParseOptions(
    # Table and image extraction
    extract_tables=True,        # Extract tables from documents
    extract_images=True,        # Extract image metadata
    extract_metadata=True,      # Extract document metadata
    
    # OCR settings
    ocr_enabled=False,          # Enable OCR for scanned content
    ocr_language="eng",         # OCR language code
    ocr_timeout=30,             # OCR timeout in seconds
    
    # Text processing
    preserve_whitespace=False,  # Preserve original whitespace
    include_formatting=False,   # Include formatting information
    renderer="auto",            # auto | markdownit | native | markitdown
    extract_links=False,        # Extract hyperlinks when supported
    
    # Selective extraction
    page_numbers=[1, 2, 3],     # Extract specific pages only
    max_pages=10,               # Maximum pages to process
    
    # Text encoding (for text files)
    encoding=None,              # Auto-detect if None

    # Attachments
    attachment_root="./bundle/attachments",  # Persist attachments under this path
    include_binary_payloads=False,           # Retain attachment bytes in the returned bundle

    # Handwriting
    handwriting_enabled=False,  # Toggle handwriting models (implies OCR is enabled)
)

result = parser.parse("document.pdf", options)
```

### Check File Support

```python
# Check if a file can be parsed
if factory.can_parse("document.xyz"):
    parser = factory.get_parser_for_file("document.xyz")
    result = parser.parse("document.xyz")
else:
    print("File format not supported")

# Get supported formats
formats = factory.get_supported_formats()
print(f"Extensions: {formats['extensions']}")
print(f"MIME types: {formats['mime_types']}")
print(f"Parsers: {formats['parsers']}")

# List all parsers
for name, info in factory.list_parsers().items():
    print(f"{name}: {info['extensions']}")
```

## Data Models & Manifest

- **ExtractedDocument** – parser output containing raw text, tables, metadata, email metadata, and attachment nodes.
- **BundleNode** – Pydantic model describing each document/attachment node (`name`, `file_type`, `markdown`, `location`, `children`).
- **DocumentBundle** – wrapper returned by the pipeline; includes the root node, attachment directory, serialisable manifest, and resolved options.

```python
from ff_parsers.models import BundleNode, DocumentBundle

bundle = pipeline.ingest("memo.eml", ParseOptions())
root: BundleNode = bundle.document
manifest = bundle.to_manifest()

print(root.markdown)  # Markdown for the main document
for attachment in bundle.iter_attachments():
    print(attachment.name, attachment.location)
```

Manifests follow the shape:

```json
{
  "created_at": "...",
  "source_path": "/absolute/path/to/file.eml",
  "attachments_dir": "/absolute/path/to/bundle/attachments",
  "document": {
    "id": "...",
    "name": "file.eml",
    "markdown": "# Email ...",
    "location": null,
    "file_type": ".eml",
    "mime_type": "message/rfc822",
    "sub_files": [
      {
        "id": "...",
        "name": "invoice.pdf",
        "location": "memo_attachments/invoice.pdf",
        "markdown": "Attachment: invoice.pdf (application/pdf)",
        "sub_files": []
      }
    ]
  }
}
```

## Supported Formats

| Format | Extensions | Features |
|--------|-----------|----------|
| PDF | .pdf | Text, tables, images, OCR support |
| Excel | .xlsx, .xls, .csv | Sheets, tables, formulas |
| Word | .docx | Text, tables, images, metadata |
| Email | .eml | Headers, body, manifest + attachment payloads |
| Text | .txt, .md, .rst, .log | Encoding detection, line tracking |

## Error Handling

The library is designed to extract as much content as possible even when errors occur:

```python
try:
    result = parser.parse("corrupted.pdf")
    
    # Partial results may be available
    if result.text:
        print(f"Extracted {len(result.text)} characters")
    
    # Check for errors
    if result.errors:
        print(f"Errors: {result.errors}")
        
except UnsupportedFormatError as e:
    print(f"Format not supported: {e}")
    
except CorruptedFileError as e:
    print(f"File is corrupted: {e}")
    # Partial results may be available
    if e.partial_result:
        print(f"Partial content: {e.partial_result.text[:100]}")
```

## Performance Tips

1. **Large Files**: Use `max_pages` option to limit processing
2. **OCR**: Disable OCR if not needed (it's slow)
3. **Memory**: Image data is not stored by default to save memory
4. **Selective Extraction**: Use `page_numbers` to extract specific pages

## Development

### Running Tests

```bash
cd ff-parsers
pytest tests/
```

### Building

```bash
cd ff-parsers
python -m build
```

## License

Proprietary - Fenixflow Internal Use Only
