"""Tests for ERD builder."""

from typing import Optional
from uuid import UUID


from ff_storage import Field, PydanticModel
from ff_storage.erd import (
    ERDBuilder,
    ERDColumn,
    ERDRelationship,
    ERDResponse,
    ERDTable,
    to_mermaid,
    to_mermaid_compact,
)


class Author(PydanticModel):
    """Test Author model."""

    __table_name__ = "authors"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False

    name: str = Field(max_length=255)
    email: str = Field(max_length=255, json_schema_extra={"db_unique": True})
    bio: Optional[str] = Field(default=None, max_length=1000)


class Post(PydanticModel):
    """Test Post model with FK to Author."""

    __table_name__ = "posts"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False

    title: str = Field(max_length=255)
    content: str = Field(max_length=10000)
    author_id: UUID = Field(json_schema_extra={"db_foreign_key": "authors.id"})
    views: int = Field(default=0, ge=0)


class Tag(PydanticModel):
    """Test Tag model."""

    __table_name__ = "tags"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False

    name: str = Field(max_length=100, json_schema_extra={"db_unique": True})


class TestERDModels:
    """Tests for ERD data models."""

    def test_erd_column_creation(self):
        """ERDColumn should create correctly."""
        column = ERDColumn(
            name="email",
            type="VARCHAR(255)",
            nullable=False,
            is_primary_key=False,
            is_foreign_key=False,
            description="User email",
        )

        assert column.name == "email"
        assert column.type == "VARCHAR(255)"
        assert column.nullable is False
        assert column.is_primary_key is False
        assert column.description == "User email"

    def test_erd_table_creation(self):
        """ERDTable should create correctly."""
        columns = [
            ERDColumn(name="id", type="UUID", nullable=False, is_primary_key=True),
            ERDColumn(name="name", type="VARCHAR(255)", nullable=False),
        ]

        table = ERDTable(
            name="users",
            schema_name="public",
            model_class="User",
            is_multi_tenant=False,
            temporal_strategy="none",
            columns=columns,
        )

        assert table.name == "users"
        assert table.schema_name == "public"
        assert table.model_class == "User"
        assert len(table.columns) == 2

    def test_erd_relationship_creation(self):
        """ERDRelationship should create correctly."""
        rel = ERDRelationship(
            from_table="posts",
            from_column="author_id",
            to_table="authors",
            to_column="id",
            relationship_type="many_to_one",
            cardinality="N:1",
        )

        assert rel.from_table == "posts"
        assert rel.to_table == "authors"
        assert rel.relationship_type == "many_to_one"
        assert rel.cardinality == "N:1"

    def test_erd_response_creation(self):
        """ERDResponse should create correctly."""
        response = ERDResponse(
            tables=[],
            relationships=[],
            schemas=["public"],
        )

        assert response.schemas == ["public"]
        assert response.tables == []
        assert response.relationships == []


class TestERDBuilder:
    """Tests for ERDBuilder."""

    def test_builder_initialization(self):
        """ERDBuilder should initialize correctly."""
        builder = ERDBuilder()
        assert builder is not None

    def test_builder_register_model(self):
        """Builder should register models correctly."""
        builder = ERDBuilder()
        builder.register_model(Author)
        builder.register_model(Post)

        assert "authors" in builder._models
        assert "posts" in builder._models

    def test_builder_build(self):
        """Builder should build ERD from registered models."""
        builder = ERDBuilder()
        builder.register_model(Author)
        builder.register_model(Post)

        erd = builder.build()

        assert isinstance(erd, ERDResponse)
        # At least 2 tables (may be more due to auto-discovery)
        assert len(erd.tables) >= 2

        # Find authors table
        authors_table = next((t for t in erd.tables if t.name == "authors"), None)
        assert authors_table is not None
        assert any(c.name == "id" for c in authors_table.columns)
        assert any(c.name == "name" for c in authors_table.columns)
        assert any(c.name == "email" for c in authors_table.columns)

    def test_builder_detect_relationships(self):
        """Builder should detect FK relationships."""
        builder = ERDBuilder()
        builder.register_model(Author)
        builder.register_model(Post)

        erd = builder.build()

        # Should detect posts.author_id -> authors.id relationship
        assert len(erd.relationships) > 0

        rel = next(
            (
                r
                for r in erd.relationships
                if r.from_table == "posts" and r.from_column == "author_id"
            ),
            None,
        )
        assert rel is not None
        assert rel.to_table == "authors"
        assert rel.to_column == "id"

    def test_builder_get_model_class(self):
        """Builder should return registered model class."""
        builder = ERDBuilder()
        builder.register_model(Author)

        model_class = builder.get_model_class("authors")
        assert model_class is Author

        unknown = builder.get_model_class("nonexistent")
        assert unknown is None

    def test_builder_schema_filter(self):
        """Builder should filter by schema."""
        builder = ERDBuilder()
        builder.register_model(Author)
        builder.register_model(Post)

        erd = builder.build(schema_filter="public")

        assert "public" in erd.schemas
        assert all(t.schema_name == "public" for t in erd.tables)


class TestMermaidGeneration:
    """Tests for Mermaid diagram generation."""

    def test_to_mermaid_basic(self):
        """to_mermaid should generate valid Mermaid syntax."""
        builder = ERDBuilder()
        builder.register_model(Author)
        builder.register_model(Post)

        erd = builder.build()
        mermaid = to_mermaid(erd)

        assert "erDiagram" in mermaid
        assert "authors" in mermaid
        assert "posts" in mermaid

    def test_to_mermaid_compact(self):
        """to_mermaid_compact should generate compact diagram."""
        builder = ERDBuilder()
        builder.register_model(Author)
        builder.register_model(Post)

        erd = builder.build()
        mermaid = to_mermaid_compact(erd)

        assert "erDiagram" in mermaid
        assert "authors" in mermaid
        assert "posts" in mermaid

    def test_to_mermaid_relationships(self):
        """Mermaid should include relationship notation."""
        builder = ERDBuilder()
        builder.register_model(Author)
        builder.register_model(Post)

        erd = builder.build()
        mermaid = to_mermaid(erd)

        # Should have relationship lines
        # posts ||--o{ authors or similar
        assert "||" in mermaid or "--" in mermaid or "}o" in mermaid or "o{" in mermaid

    def test_to_mermaid_column_types(self):
        """Mermaid should include column types."""
        builder = ERDBuilder()
        builder.register_model(Author)

        erd = builder.build()
        mermaid = to_mermaid(erd)

        # Should mention column types
        assert "uuid" in mermaid.lower() or "string" in mermaid.lower()
