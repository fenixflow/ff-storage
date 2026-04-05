"""Mermaid ERD diagram generation.

Converts ERDResponse data to Mermaid diagram syntax for visualization.

Example:
    >>> from ff_storage.erd import ERDBuilder, to_mermaid
    >>> builder = ERDBuilder()
    >>> erd = builder.build()
    >>> print(to_mermaid(erd))
    erDiagram
        users ||--o{ posts : "author_id"
        users {
            uuid id PK
            string email
            string name
        }
        ...
"""

from .models import ERDResponse


def to_mermaid(erd: ERDResponse) -> str:
    """Generate Mermaid ERD syntax from ERD data.

    Args:
        erd: ERD response data

    Returns:
        Mermaid diagram syntax string

    Example output:
        erDiagram
            users ||--o{ posts : "author_id"

            users {
                uuid id PK
                string email
                string name
            }
            posts {
                uuid id PK
                string title
                uuid author_id FK
            }
    """
    lines = ["erDiagram"]

    # Add relationships first
    cardinality_symbols = {
        "1:1": "||--||",
        "1:N": "||--o{",
        "N:1": "}o--||",
        "N:M": "}o--o{",
    }

    for rel in erd.relationships:
        symbol = cardinality_symbols.get(rel.cardinality, "||--o{")
        lines.append(f'    {rel.from_table} {symbol} {rel.to_table} : "{rel.from_column}"')

    # Add empty line between relationships and tables
    if erd.relationships:
        lines.append("")

    # Add table definitions
    for table in erd.tables:
        lines.append(f"    {table.name} {{")
        for col in table.columns:
            pk = "PK" if col.is_primary_key else ""
            fk = "FK" if col.is_foreign_key else ""
            modifier = pk or fk
            col_def = f"        {col.type} {col.name}"
            if modifier:
                col_def += f" {modifier}"
            lines.append(col_def)
        lines.append("    }")

    return "\n".join(lines)


def to_mermaid_compact(erd: ERDResponse) -> str:
    """Generate compact Mermaid ERD with relationships only.

    Useful for large schemas where table details clutter the diagram.

    Args:
        erd: ERD response data

    Returns:
        Mermaid diagram syntax showing only relationships
    """
    lines = ["erDiagram"]

    cardinality_symbols = {
        "1:1": "||--||",
        "1:N": "||--o{",
        "N:1": "}o--||",
        "N:M": "}o--o{",
    }

    for rel in erd.relationships:
        symbol = cardinality_symbols.get(rel.cardinality, "||--o{")
        lines.append(f'    {rel.from_table} {symbol} {rel.to_table} : "{rel.from_column}"')

    return "\n".join(lines)
