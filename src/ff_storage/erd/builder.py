"""ERD (Entity Relationship Diagram) builder for model introspection.

Discovers PydanticModel subclasses with __table_name__ attributes,
extracts schema information, and generates ERD data.

Example:
    >>> from ff_storage.erd import ERDBuilder
    >>> builder = ERDBuilder()
    >>> erd = builder.build()
    >>> print(builder.to_mermaid(erd))
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, get_args, get_origin
from uuid import UUID

from .models import ERDColumn, ERDRelationship, ERDResponse, ERDTable

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel


class ERDBuilder:
    """Builds ERD data from PydanticModel introspection.

    The builder discovers all PydanticModel subclasses and extracts:
    - Table names and schemas
    - Column definitions with types and constraints
    - Foreign key relationships

    Example:
        >>> builder = ERDBuilder()
        >>> builder.register_model(User)  # Optional: manual registration
        >>> erd = builder.build(schema_filter="public")
        >>> mermaid = builder.to_mermaid(erd)
    """

    # Known FK field name to table name mappings
    # Add common patterns here; users can extend via register_fk_mapping()
    FK_TABLE_MAPPINGS: dict[str, str | None] = {
        "tenant_id": None,  # Not a table FK
        "created_by": None,  # User reference but often UUID only
        "updated_by": None,
        "deleted_by": None,
    }

    def __init__(self, auto_discover: bool = True):
        """Initialize ERD builder.

        Args:
            auto_discover: If True, automatically discover PydanticModel subclasses.
                          If False, use register_model() to add models manually.
        """
        self._models: dict[str, type[PydanticModel]] = {}
        self._fk_mappings: dict[str, str | None] = dict(self.FK_TABLE_MAPPINGS)

        if auto_discover:
            self._discover_models()

    def _discover_models(self) -> None:
        """Discover all PydanticModel subclasses with __table_name__."""
        from ..pydantic_support.base import PydanticModel

        def find_subclasses(cls: type) -> set[type]:
            subclasses = set()
            for subclass in cls.__subclasses__():
                subclasses.add(subclass)
                subclasses.update(find_subclasses(subclass))
            return subclasses

        all_subclasses = find_subclasses(PydanticModel)

        for model_class in all_subclasses:
            table_name = getattr(model_class, "__table_name__", None)
            if table_name:
                self._models[table_name] = model_class

    def register_model(self, model_class: type[PydanticModel]) -> None:
        """Manually register a model for ERD generation.

        Args:
            model_class: A PydanticModel subclass with __table_name__
        """
        table_name = getattr(model_class, "__table_name__", None)
        if table_name:
            self._models[table_name] = model_class

    def register_fk_mapping(self, field_name: str, table_name: str | None) -> None:
        """Register a custom FK field to table mapping.

        Args:
            field_name: The FK field name (e.g., "category_id")
            table_name: The target table name (e.g., "categories"), or None to ignore
        """
        self._fk_mappings[field_name] = table_name

    def _get_python_type_name(self, annotation: Any) -> str:
        """Convert Python type annotation to simple type name."""
        if annotation is None:
            return "any"

        origin = get_origin(annotation)
        args = get_args(annotation)

        # Handle Union types (including Optional)
        if origin is type(None):
            return "null"

        if hasattr(annotation, "__origin__"):
            if annotation.__origin__ is type(None):
                return "null"

        # Get the base type name
        if origin is not None:
            origin_name = getattr(origin, "__name__", str(origin))

            # Handle common containers
            if origin_name in ("list", "List"):
                if args:
                    inner = self._get_python_type_name(args[0])
                    return f"list[{inner}]"
                return "list"
            if origin_name in ("dict", "Dict"):
                return "dict"
            if origin_name == "Union":
                # Filter out NoneType for Optional
                non_none_args = [a for a in args if a is not type(None)]
                if len(non_none_args) == 1:
                    return self._get_python_type_name(non_none_args[0])
                return "union"

            return origin_name.lower()

        # Simple types
        if hasattr(annotation, "__name__"):
            name = annotation.__name__
            type_map = {
                "str": "string",
                "int": "integer",
                "float": "number",
                "bool": "boolean",
                "UUID": "uuid",
                "datetime": "datetime",
                "date": "date",
                "Decimal": "decimal",
                "NoneType": "null",
            }
            return type_map.get(name, name.lower())

        return str(annotation).lower()

    def _is_uuid_type(self, annotation: Any) -> bool:
        """Check if type annotation is UUID or Optional[UUID]."""
        if annotation is UUID:
            return True

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is not None and args:
            # Check Union[UUID, None] (Optional[UUID])
            return UUID in args

        return False

    def _is_list_uuid_type(self, annotation: Any) -> bool:
        """Check if type annotation is list[UUID]."""
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin in (list, list) and args:
            return args[0] is UUID

        return False

    def _extract_table(self, table_name: str, model_class: type[PydanticModel]) -> ERDTable:
        """Extract table information from model class."""
        schema_name = getattr(model_class, "__schema__", "public")
        is_multi_tenant = getattr(model_class, "__multi_tenant__", False)
        temporal_strategy = getattr(model_class, "__temporal_strategy__", None)

        columns: list[ERDColumn] = []

        # Get system fields that are auto-injected (currently unused but kept for future)
        if hasattr(model_class, "get_system_fields"):
            _ = model_class.get_system_fields()  # noqa: F841

        # Add model-defined fields (which includes injected temporal fields)
        if hasattr(model_class, "model_fields"):
            for field_name, field_info in model_class.model_fields.items():
                annotation = field_info.annotation
                type_name = self._get_python_type_name(annotation)

                # Determine if nullable
                nullable = False
                if get_origin(annotation) is type(None):
                    nullable = True
                args = get_args(annotation)
                if args and type(None) in args:
                    nullable = True
                if field_info.default is None and not field_info.is_required():
                    nullable = True

                # Check metadata for explicit nullable override
                metadata = field_info.json_schema_extra or {}
                if "db_nullable" in metadata:
                    nullable = metadata["db_nullable"]

                # Check if primary key
                is_pk = field_name == "id" or metadata.get("db_primary_key", False)

                # Check if foreign key
                is_fk = field_name.endswith("_id") and self._is_uuid_type(annotation)
                # Exclude known non-FK fields
                if field_name in self._fk_mappings and self._fk_mappings[field_name] is None:
                    is_fk = False

                columns.append(
                    ERDColumn(
                        name=field_name,
                        type=type_name,
                        nullable=nullable,
                        is_primary_key=is_pk,
                        is_foreign_key=is_fk,
                        description=field_info.description,
                    )
                )

        return ERDTable(
            name=table_name,
            schema_name=schema_name,
            model_class=model_class.__name__,
            is_multi_tenant=is_multi_tenant,
            temporal_strategy=temporal_strategy,
            columns=columns,
        )

    def _infer_target_table(self, field_name: str) -> str | None:
        """Infer target table from FK field name."""
        # Check explicit mapping first
        if field_name in self._fk_mappings:
            return self._fk_mappings[field_name]

        # Handle list FK fields (e.g., binder_section_ids -> binder_sections)
        if field_name.endswith("_ids"):
            base_name = field_name[:-4]  # Remove "_ids"
            # Try common pluralization patterns
            if base_name.endswith("y"):
                return base_name[:-1] + "ies"  # category_ids -> categories
            return base_name + "s"  # section_ids -> sections

        # Handle single FK fields (e.g., rule_id -> rules)
        if field_name.endswith("_id"):
            base_name = field_name[:-3]  # Remove "_id"
            # Try common pluralization patterns
            if base_name.endswith("y"):
                return base_name[:-1] + "ies"
            if base_name.endswith("s"):
                return base_name + "es"
            return base_name + "s"

        return None

    def _detect_relationships(self) -> list[ERDRelationship]:
        """Detect FK relationships from field patterns."""
        relationships: list[ERDRelationship] = []

        for table_name, model_class in self._models.items():
            if not hasattr(model_class, "model_fields"):
                continue

            for field_name, field_info in model_class.model_fields.items():
                annotation = field_info.annotation

                # Pattern 1: UUID field ending in _id -> FK (many-to-one)
                if field_name.endswith("_id") and self._is_uuid_type(annotation):
                    # Skip known non-FK fields
                    if field_name in self._fk_mappings and self._fk_mappings[field_name] is None:
                        continue

                    target_table = self._infer_target_table(field_name)
                    if target_table and target_table in self._models:
                        relationships.append(
                            ERDRelationship(
                                from_table=table_name,
                                from_column=field_name,
                                to_table=target_table,
                                to_column="id",
                                relationship_type="many_to_one",
                                cardinality="N:1",
                            )
                        )

                # Pattern 2: list[UUID] field ending in _ids -> M:M
                elif field_name.endswith("_ids") and self._is_list_uuid_type(annotation):
                    target_table = self._infer_target_table(field_name)
                    if target_table and target_table in self._models:
                        relationships.append(
                            ERDRelationship(
                                from_table=table_name,
                                from_column=field_name,
                                to_table=target_table,
                                to_column="id",
                                relationship_type="many_to_many",
                                cardinality="N:M",
                            )
                        )

        return relationships

    def build(self, schema_filter: str | None = None) -> ERDResponse:
        """Build ERD data from discovered models.

        Args:
            schema_filter: Optional filter to only include tables from specific DB schema

        Returns:
            ERDResponse with tables and relationships
        """
        tables: list[ERDTable] = []
        schemas: set[str] = set()

        for table_name, model_class in self._models.items():
            table = self._extract_table(table_name, model_class)

            # Apply schema filter if provided
            if schema_filter and table.schema_name != schema_filter:
                continue

            tables.append(table)
            schemas.add(table.schema_name)

        # Sort tables by schema then name
        tables.sort(key=lambda t: (t.schema_name, t.name))

        # Detect relationships
        all_relationships = self._detect_relationships()

        # Filter relationships to only include tables in result
        table_names = {t.name for t in tables}
        relationships = [
            r
            for r in all_relationships
            if r.from_table in table_names and r.to_table in table_names
        ]

        return ERDResponse(
            tables=tables,
            relationships=relationships,
            schemas=sorted(schemas),
        )

    def get_model_class(self, table_name: str) -> type | None:
        """Get model class by table name.

        Args:
            table_name: Database table name (e.g., "programs", "sui")

        Returns:
            The Pydantic model class, or None if not found
        """
        return self._models.get(table_name)

    @property
    def model_registry(self) -> dict[str, type]:
        """Get all discovered model classes.

        Returns:
            Dictionary mapping table names to model classes
        """
        return dict(self._models)
