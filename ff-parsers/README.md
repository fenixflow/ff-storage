# ff-parsers

A lightweight document parsing library for extracting content from various file formats with basic provenance tracking.

## Features

- **Multiple Format Support**: PDF, Excel (xlsx/xls/csv), Word (docx), Email (eml), and plain text files
- **Simple Provenance**: Track page numbers, sheet names, and paragraph locations
- **Table Extraction**: Extract structured table data from documents
- **Metadata Extraction**: Get document properties and metadata
- **OCR Support**: Optional OCR for scanned PDFs using pytesseract
- **Encoding Detection**: Automatic encoding detection for text files
- **Clean API**: Simple, consistent interface across all parsers

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

### Basic Usage

```python
from ff_parsers import ParserFactory

# Create factory
factory = ParserFactory()

# Auto-detect file type and parse
parser = factory.get_parser_for_file("document.pdf")
result = parser.parse("document.pdf")

# Access extracted content
print(result.text)  # Full text
print(f"Pages: {result.page_count}")
print(f"Tables: {result.table_count}")

# Access metadata
print(f"Title: {result.metadata.title}")
print(f"Author: {result.metadata.author}")
print(f"Created: {result.metadata.created_date}")
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
    
    # Selective extraction
    page_numbers=[1, 2, 3],     # Extract specific pages only
    max_pages=10,               # Maximum pages to process
    
    # Text encoding (for text files)
    encoding=None,              # Auto-detect if None
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

## Data Models

### ExtractedDocument

The main result object containing all extracted content:

```python
@dataclass
class ExtractedDocument:
    text: str                           # Full extracted text
    pages: List[ExtractedText]          # Page/section-wise text
    tables: List[ExtractedTable]        # Extracted tables
    images: List[ExtractedImage]        # Image metadata
    metadata: DocumentMetadata          # Document metadata
    email_metadata: Optional[EmailMetadata]  # Email-specific metadata
    file_path: Optional[str]            # Original file path
    file_hash: Optional[str]            # SHA-256 hash
    extraction_timestamp: Optional[datetime]
    parser_version: Optional[str]
    errors: List[str]                   # Non-fatal errors
    warnings: List[str]                 # Warnings
```

### ExtractedText

Text with location information:

```python
@dataclass
class ExtractedText:
    content: str                # The text content
    page: Optional[int]         # Page number (1-indexed)
    paragraph: Optional[int]    # Paragraph number
    line: Optional[int]         # Line number
    sheet: Optional[str]        # Excel sheet name
    confidence: float = 1.0     # Confidence score (0.0-1.0)
```

### ExtractedTable

Structured table data:

```python
@dataclass
class ExtractedTable:
    headers: List[str]          # Column headers
    rows: List[List[str]]       # Data rows
    page: Optional[int]         # Page where table appears
    sheet: Optional[str]        # Excel sheet name
    name: Optional[str]         # Table name/identifier
    cell_range: Optional[str]   # Excel cell range (e.g., "A1:D10")
```

## Supported Formats

| Format | Extensions | Features |
|--------|-----------|----------|
| PDF | .pdf | Text, tables, images, OCR support |
| Excel | .xlsx, .xls, .csv | Sheets, tables, formulas |
| Word | .docx | Text, tables, images, metadata |
| Email | .eml | Headers, body, attachments list |
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