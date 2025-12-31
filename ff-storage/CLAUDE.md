# CLAUDE.md - ff-storage Relationships & Query Builder Implementation

## Mission

You are implementing **Relationships** and **Query Builder** features for ff-storage, a Pydantic-first ORM with built-in temporal versioning. Your implementation must be **100% non-breaking and additive** - all existing code must continue working unchanged.

## Critical Constraints

1. **Non-Breaking**: No changes to existing method signatures or behavior
2. **Additive Only**: New directories, new classes, new optional parameters
3. **Opt-In Features**: Old `repo.list(filters={})` API unchanged
4. **Temporal-Aware**: JOINs must handle SCD2 `valid_to IS NULL` filtering
5. **Multi-Tenant Safe**: JOINs must include tenant isolation

## Git Commit Guidelines

**CRITICAL: ALL commits must appear to be made entirely by the human developer.**

- NEVER add Claude, AI, or any AI attribution as author or co-author
- ALWAYS use existing git config: `Ben <ben@fenixflow.com>`
- Follow conventional commit format: `feat:`, `fix:`, `test:`, `docs:`

---

## Current Architecture Overview

### Key Files to Understand

```
src/ff_storage/
├── pydantic_support/
│   ├── base.py              # PydanticModel base class (MODIFY)
│   ├── repository.py        # PydanticRepository (READ ONLY)
│   └── schema_sync.py       # Schema synchronization (READ ONLY)
├── temporal/
│   ├── repository.py        # TemporalRepository base
│   └── strategies/
│       ├── base.py          # BaseTemporalStrategy
│       ├── scd2.py          # SCD2Strategy - key for understanding temporal queries
│       ├── copy_on_change.py
│       └── none.py
├── db/
│   ├── query_builder/
│   │   ├── base.py          # QueryBuilder abstract base (MODIFY)
│   │   └── postgres.py      # PostgresQueryBuilder (MODIFY)
│   └── pool/
│       └── postgres.py      # PostgresPool connection management
└── __init__.py              # Package exports (MODIFY)
```

### PydanticModel Base Class

```python
# From pydantic_support/base.py - Key attributes
class PydanticModel(BaseModel):
    __table_name__: ClassVar[str]           # Required: database table name
    __schema__: ClassVar[str] = "public"    # Database schema
    __temporal_strategy__: ClassVar[str] = "none"  # "none", "scd2", "copy_on_change"
    __soft_delete__: ClassVar[bool] = True
    __multi_tenant__: ClassVar[bool] = True

    # Standard fields (auto-managed)
    id: UUID
    tenant_id: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    # SCD2 fields (when temporal_strategy="scd2")
    valid_from: datetime
    valid_to: datetime | None  # NULL = current version
```

### Temporal Strategies

| Strategy | Behavior | Current Record Filter |
|----------|----------|----------------------|
| `none` | No versioning | No temporal filter |
| `scd2` | Full history in same table | `valid_to IS NULL` |
| `copy_on_change` | Current in main, history in audit | No temporal filter on main |

### Repository Pattern

```python
# Current usage - must remain unchanged
repo = PydanticRepository(Product, db_pool, tenant_id=tenant)
products = await repo.list(filters={"status": "active"})  # OLD API - keep working
product = await repo.get(product_id)
await repo.create(product)
await repo.update(product_id, {"price": 100})
```

---

## Target API (What You're Building)

### Relationship Definition

```python
from ff_storage.relationships import Relationship

class Author(PydanticModel):
    __table_name__ = "authors"

    name: str = Field(max_length=255)

    # NEW: Relationship definition (virtual field, not in DB)
    posts: List["Post"] = Relationship(back_populates="author")

class Post(PydanticModel):
    __table_name__ = "posts"

    title: str = Field(max_length=255)
    author_id: UUID = Field(json_schema_extra={"db_foreign_key": "authors.id"})

    # NEW: Back-reference
    author: "Author" = Relationship(back_populates="posts")
```

### Query Builder with JOINs

```python
from ff_storage.query import Query

# Fluent query API with type-safe filtering
results = await (
    Query(Author)
    .filter(Author.name.contains("John"))
    .join(Author.posts)
    .filter(Post.published == True)
    .order_by(Author.created_at.desc())
    .load(["posts"])  # Eager load to prevent N+1
    .limit(10)
    .execute(db_pool, tenant_id=tenant)
)

# Simple filtering
products = await (
    Query(Product)
    .filter(Product.price > 100)
    .filter(Product.status == "active")
    .order_by(Product.created_at.desc())
    .execute(db_pool, tenant_id=tenant)
)

# Aggregations
count = await Query(Product).filter(Product.active == True).count(db_pool)
```

---

## Files to Create

### 1. `src/ff_storage/relationships/__init__.py`

```python
"""Relationship definitions for ff-storage models."""

from .descriptor import Relationship
from .config import RelationshipConfig
from .registry import RelationshipRegistry
from .loader import RelationshipLoader

__all__ = [
    "Relationship",
    "RelationshipConfig",
    "RelationshipRegistry",
    "RelationshipLoader",
]
```

### 2. `src/ff_storage/relationships/config.py`

```python
"""Relationship configuration dataclass."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel


@dataclass
class RelationshipConfig:
    """Configuration for a model relationship."""

    # Core configuration
    target_model: str  # String reference to avoid circular imports
    back_populates: str | None = None
    foreign_key: str | None = None  # Auto-detected if not provided

    # For many-to-many relationships
    link_model: str | None = None
    link_local_key: str | None = None
    link_remote_key: str | None = None

    # Loading behavior
    lazy: str = "select"  # "select", "joined", "subquery", "noload"

    # Relationship type (auto-detected from type hints)
    is_collection: bool = False  # True for List[Model], False for Model

    # Ordering
    order_by: str | None = None

    # Metadata
    owner_model: str | None = None
    attribute_name: str | None = None

    def get_foreign_key_column(self) -> str:
        """Get the foreign key column name."""
        if self.foreign_key:
            return self.foreign_key

        # Auto-detect: if this is a collection, FK is on target
        # If this is a reference, FK is on owner
        if self.is_collection:
            # posts on Author -> Post.author_id
            owner_table = self.owner_model.lower() if self.owner_model else ""
            return f"{owner_table}_id"
        else:
            # author on Post -> Post.author_id
            return f"{self.attribute_name}_id" if self.attribute_name else ""
```

### 3. `src/ff_storage/relationships/descriptor.py`

```python
"""Relationship descriptor for PydanticModel classes."""

from typing import TYPE_CHECKING, Any, Generic, TypeVar, get_args, get_origin
import weakref

from .config import RelationshipConfig
from .registry import RelationshipRegistry

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel

T = TypeVar("T", bound="PydanticModel")


class Relationship(Generic[T]):
    """
    Descriptor for defining relationships between PydanticModel classes.

    Usage:
        class Author(PydanticModel):
            posts: List["Post"] = Relationship(back_populates="author")

        class Post(PydanticModel):
            author_id: UUID
            author: "Author" = Relationship(back_populates="posts")
    """

    def __init__(
        self,
        *,
        back_populates: str | None = None,
        foreign_key: str | None = None,
        link_model: str | None = None,
        link_local_key: str | None = None,
        link_remote_key: str | None = None,
        lazy: str = "select",
        order_by: str | None = None,
    ):
        """
        Initialize a relationship.

        Args:
            back_populates: Name of the reverse relationship on the target model
            foreign_key: Explicit foreign key column (auto-detected if not provided)
            link_model: For many-to-many, the junction table model name
            link_local_key: For many-to-many, FK column pointing to this model
            link_remote_key: For many-to-many, FK column pointing to target model
            lazy: Loading strategy ("select", "joined", "subquery", "noload")
            order_by: Default ordering for collection relationships
        """
        self.back_populates = back_populates
        self.foreign_key = foreign_key
        self.link_model = link_model
        self.link_local_key = link_local_key
        self.link_remote_key = link_remote_key
        self.lazy = lazy
        self.order_by = order_by

        # Set by __set_name__
        self._name: str | None = None
        self._owner: type | None = None
        self._config: RelationshipConfig | None = None

        # Cache for loaded relationships (weakref to avoid memory leaks)
        self._cache: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def __set_name__(self, owner: type, name: str) -> None:
        """Called when the descriptor is assigned to a class attribute."""
        self._name = name
        self._owner = owner

        # Get type hint to determine if this is a collection
        annotations = getattr(owner, "__annotations__", {})
        type_hint = annotations.get(name)

        is_collection = False
        target_model = ""

        if type_hint:
            origin = get_origin(type_hint)
            if origin is list:
                is_collection = True
                args = get_args(type_hint)
                if args:
                    target_model = args[0] if isinstance(args[0], str) else args[0].__name__
            else:
                target_model = type_hint if isinstance(type_hint, str) else getattr(type_hint, "__name__", str(type_hint))

        # Create configuration
        self._config = RelationshipConfig(
            target_model=target_model,
            back_populates=self.back_populates,
            foreign_key=self.foreign_key,
            link_model=self.link_model,
            link_local_key=self.link_local_key,
            link_remote_key=self.link_remote_key,
            lazy=self.lazy,
            is_collection=is_collection,
            order_by=self.order_by,
            owner_model=owner.__name__,
            attribute_name=name,
        )

        # Register with the global registry
        RelationshipRegistry.register(owner.__name__, name, self._config)

        # Store on the class for introspection
        if not hasattr(owner, "_relationships"):
            owner._relationships = {}
        owner._relationships[name] = self._config

    def __get__(self, instance: Any, owner: type) -> Any:
        """Get the relationship value."""
        if instance is None:
            # Class-level access returns the descriptor for query building
            return RelationshipProxy(self._name, self._config, owner)

        # Instance-level access returns cached data or None
        return self._cache.get(instance)

    def __set__(self, instance: Any, value: Any) -> None:
        """Set the relationship value (used by loader)."""
        self._cache[instance] = value

    @property
    def config(self) -> RelationshipConfig | None:
        """Get the relationship configuration."""
        return self._config


class RelationshipProxy:
    """
    Proxy returned when accessing a relationship at class level.
    Used for building queries with joins.
    """

    def __init__(self, name: str, config: RelationshipConfig, owner: type):
        self.name = name
        self.config = config
        self.owner = owner

    def __repr__(self) -> str:
        return f"<RelationshipProxy {self.owner.__name__}.{self.name}>"
```

### 4. `src/ff_storage/relationships/registry.py`

```python
"""Global registry for model relationships."""

from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import RelationshipConfig


class RelationshipRegistry:
    """
    Global registry mapping model names to their relationships.

    This allows relationships to be resolved across modules without
    circular import issues.
    """

    _registry: Dict[str, Dict[str, "RelationshipConfig"]] = {}
    _models: Dict[str, type] = {}

    @classmethod
    def register(cls, model_name: str, attr_name: str, config: "RelationshipConfig") -> None:
        """Register a relationship for a model."""
        if model_name not in cls._registry:
            cls._registry[model_name] = {}
        cls._registry[model_name][attr_name] = config

    @classmethod
    def register_model(cls, model_name: str, model_class: type) -> None:
        """Register a model class for later resolution."""
        cls._models[model_name] = model_class

    @classmethod
    def get_relationships(cls, model_name: str) -> Dict[str, "RelationshipConfig"]:
        """Get all relationships for a model."""
        return cls._registry.get(model_name, {})

    @classmethod
    def get_relationship(cls, model_name: str, attr_name: str) -> "RelationshipConfig | None":
        """Get a specific relationship configuration."""
        return cls._registry.get(model_name, {}).get(attr_name)

    @classmethod
    def resolve_model(cls, model_name: str) -> type | None:
        """Resolve a model name to its class."""
        return cls._models.get(model_name)

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (useful for testing)."""
        cls._registry.clear()
        cls._models.clear()
```

### 5. `src/ff_storage/relationships/loader.py`

```python
"""Relationship loader for eager loading related objects."""

from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar
from uuid import UUID

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel
    from ..db.pool.postgres import PostgresPool

from .registry import RelationshipRegistry

T = TypeVar("T", bound="PydanticModel")


class RelationshipLoader:
    """
    Loads relationships for a set of model instances.

    Uses the "selectinload" pattern - batch loading with IN clauses
    to prevent N+1 query problems.
    """

    def __init__(self, model_class: Type[T]):
        self.model_class = model_class
        self.model_name = model_class.__name__

    async def load_relationships(
        self,
        instances: List[T],
        relationship_names: List[str],
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
    ) -> List[T]:
        """
        Load specified relationships for a list of instances.

        Args:
            instances: List of model instances to load relationships for
            relationship_names: Names of relationships to load
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            The same instances with relationships populated
        """
        if not instances:
            return instances

        for rel_name in relationship_names:
            config = RelationshipRegistry.get_relationship(self.model_name, rel_name)
            if not config:
                raise ValueError(f"Unknown relationship: {self.model_name}.{rel_name}")

            await self._load_relationship(instances, rel_name, config, db_pool, tenant_id)

        return instances

    async def _load_relationship(
        self,
        instances: List[T],
        rel_name: str,
        config: "RelationshipConfig",
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
    ) -> None:
        """Load a single relationship for all instances."""
        from ..pydantic_support.repository import PydanticRepository

        # Resolve target model
        target_model = RelationshipRegistry.resolve_model(config.target_model)
        if not target_model:
            raise ValueError(f"Cannot resolve model: {config.target_model}")

        # Get IDs from instances
        instance_ids = [inst.id for inst in instances]

        if config.is_collection:
            # One-to-many: target has FK pointing to this model
            fk_column = config.get_foreign_key_column()

            # Batch query: SELECT * FROM posts WHERE author_id IN (...)
            repo = PydanticRepository(target_model, db_pool, tenant_id=tenant_id)
            related = await repo.list(filters={fk_column: {"$in": instance_ids}})

            # Group by foreign key
            grouped: Dict[UUID, List] = {id_: [] for id_ in instance_ids}
            for item in related:
                fk_value = getattr(item, fk_column, None)
                if fk_value and fk_value in grouped:
                    grouped[fk_value].append(item)

            # Assign to instances
            for inst in instances:
                rel_descriptor = getattr(type(inst), rel_name, None)
                if rel_descriptor:
                    rel_descriptor.__set__(inst, grouped.get(inst.id, []))

        else:
            # Many-to-one: this model has FK pointing to target
            fk_column = config.get_foreign_key_column()

            # Get unique FK values
            fk_values = list(set(
                getattr(inst, fk_column)
                for inst in instances
                if getattr(inst, fk_column, None)
            ))

            if not fk_values:
                return

            # Batch query: SELECT * FROM authors WHERE id IN (...)
            repo = PydanticRepository(target_model, db_pool, tenant_id=tenant_id)
            related = await repo.list(filters={"id": {"$in": fk_values}})

            # Index by ID
            related_by_id = {item.id: item for item in related}

            # Assign to instances
            for inst in instances:
                fk_value = getattr(inst, fk_column, None)
                rel_descriptor = getattr(type(inst), rel_name, None)
                if rel_descriptor and fk_value:
                    rel_descriptor.__set__(inst, related_by_id.get(fk_value))
```

### 6. `src/ff_storage/query/__init__.py`

```python
"""Query builder for ff-storage models."""

from .builder import Query
from .expressions import FilterExpression, FieldProxy, F
from .ordering import OrderByClause
from .functions import func

__all__ = [
    "Query",
    "FilterExpression",
    "FieldProxy",
    "F",
    "OrderByClause",
    "func",
]
```

### 7. `src/ff_storage/query/expressions.py`

```python
"""Filter expressions for the query builder."""

from dataclasses import dataclass
from typing import Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .ordering import OrderByClause


@dataclass
class FilterExpression:
    """
    Represents a filter condition in a query.

    Examples:
        Product.price > 100  -> FilterExpression(field="price", op=">", value=100)
        Product.name.contains("test") -> FilterExpression(field="name", op="LIKE", value="%test%")
    """

    field: str
    operator: str
    value: Any
    table_alias: str = "t0"

    def to_sql(self, param_index: int = 1) -> tuple[str, Any, int]:
        """
        Convert to SQL clause with parameter placeholder.

        Returns:
            Tuple of (sql_clause, param_value, next_param_index)
        """
        column = f"{self.table_alias}.{self.field}"

        if self.operator == "IS NULL":
            return f"{column} IS NULL", None, param_index

        if self.operator == "IS NOT NULL":
            return f"{column} IS NOT NULL", None, param_index

        if self.operator == "IN":
            if not self.value:
                return "FALSE", None, param_index  # Empty IN is always false
            placeholders = ", ".join(f"${param_index + i}" for i in range(len(self.value)))
            return f"{column} IN ({placeholders})", self.value, param_index + len(self.value)

        if self.operator == "NOT IN":
            if not self.value:
                return "TRUE", None, param_index  # Empty NOT IN is always true
            placeholders = ", ".join(f"${param_index + i}" for i in range(len(self.value)))
            return f"{column} NOT IN ({placeholders})", self.value, param_index + len(self.value)

        if self.operator == "BETWEEN":
            return (
                f"{column} BETWEEN ${param_index} AND ${param_index + 1}",
                self.value,
                param_index + 2
            )

        # Standard operators: =, !=, <, >, <=, >=, LIKE, ILIKE
        return f"{column} {self.operator} ${param_index}", self.value, param_index + 1


class FieldProxy:
    """
    Proxy for a model field that enables expression building.

    Usage:
        Product.price > 100  # Returns FilterExpression
        Product.name.contains("test")  # Returns FilterExpression
        Product.created_at.desc()  # Returns OrderByClause
    """

    def __init__(self, field_name: str, model_class: type | None = None):
        self.field_name = field_name
        self.model_class = model_class

    # Comparison operators
    def __eq__(self, other: Any) -> FilterExpression:
        if other is None:
            return FilterExpression(self.field_name, "IS NULL", None)
        return FilterExpression(self.field_name, "=", other)

    def __ne__(self, other: Any) -> FilterExpression:
        if other is None:
            return FilterExpression(self.field_name, "IS NOT NULL", None)
        return FilterExpression(self.field_name, "!=", other)

    def __lt__(self, other: Any) -> FilterExpression:
        return FilterExpression(self.field_name, "<", other)

    def __le__(self, other: Any) -> FilterExpression:
        return FilterExpression(self.field_name, "<=", other)

    def __gt__(self, other: Any) -> FilterExpression:
        return FilterExpression(self.field_name, ">", other)

    def __ge__(self, other: Any) -> FilterExpression:
        return FilterExpression(self.field_name, ">=", other)

    # String operations
    def contains(self, value: str) -> FilterExpression:
        """Case-sensitive contains (LIKE %value%)."""
        return FilterExpression(self.field_name, "LIKE", f"%{value}%")

    def icontains(self, value: str) -> FilterExpression:
        """Case-insensitive contains (ILIKE %value%)."""
        return FilterExpression(self.field_name, "ILIKE", f"%{value}%")

    def startswith(self, value: str) -> FilterExpression:
        """Starts with (LIKE value%)."""
        return FilterExpression(self.field_name, "LIKE", f"{value}%")

    def endswith(self, value: str) -> FilterExpression:
        """Ends with (LIKE %value)."""
        return FilterExpression(self.field_name, "LIKE", f"%{value}")

    # Collection operations
    def in_(self, values: List[Any]) -> FilterExpression:
        """IN clause."""
        return FilterExpression(self.field_name, "IN", list(values))

    def not_in(self, values: List[Any]) -> FilterExpression:
        """NOT IN clause."""
        return FilterExpression(self.field_name, "NOT IN", list(values))

    def between(self, low: Any, high: Any) -> FilterExpression:
        """BETWEEN clause."""
        return FilterExpression(self.field_name, "BETWEEN", (low, high))

    # Null checks
    def is_null(self) -> FilterExpression:
        """IS NULL."""
        return FilterExpression(self.field_name, "IS NULL", None)

    def is_not_null(self) -> FilterExpression:
        """IS NOT NULL."""
        return FilterExpression(self.field_name, "IS NOT NULL", None)

    # Ordering
    def asc(self) -> "OrderByClause":
        """Ascending order."""
        from .ordering import OrderByClause
        return OrderByClause(self.field_name, "ASC")

    def desc(self) -> "OrderByClause":
        """Descending order."""
        from .ordering import OrderByClause
        return OrderByClause(self.field_name, "DESC")


# Shorthand for creating field proxies
class F:
    """
    Factory for creating FieldProxy instances.

    Usage:
        F.price > 100  # Same as FieldProxy("price") > 100
    """

    def __class_getitem__(cls, field_name: str) -> FieldProxy:
        return FieldProxy(field_name)

    def __getattr__(self, field_name: str) -> FieldProxy:
        return FieldProxy(field_name)


# Create singleton instance
F = F()
```

### 8. `src/ff_storage/query/ordering.py`

```python
"""Ordering clauses for the query builder."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class OrderByClause:
    """
    Represents an ORDER BY clause.

    Examples:
        Product.created_at.desc() -> OrderByClause("created_at", "DESC")
    """

    field: str
    direction: Literal["ASC", "DESC"] = "ASC"
    nulls: Literal["FIRST", "LAST"] | None = None
    table_alias: str = "t0"

    def to_sql(self) -> str:
        """Convert to SQL ORDER BY clause."""
        sql = f"{self.table_alias}.{self.field} {self.direction}"
        if self.nulls:
            sql += f" NULLS {self.nulls}"
        return sql
```

### 9. `src/ff_storage/query/builder.py`

```python
"""Fluent query builder for ff-storage models."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, List, Type, TypeVar
from uuid import UUID

from .expressions import FilterExpression, FieldProxy
from .ordering import OrderByClause

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel
    from ..db.pool.postgres import PostgresPool
    from ..relationships.descriptor import RelationshipProxy

T = TypeVar("T", bound="PydanticModel")


@dataclass
class JoinConfig:
    """Configuration for a JOIN clause."""
    target_model: Type["PydanticModel"]
    join_type: str = "INNER"  # INNER, LEFT, RIGHT
    on_clause: str | None = None  # Auto-generated if None
    alias: str = ""
    via_relationship: str | None = None  # Relationship name if joined via relationship


class Query(Generic[T]):
    """
    Fluent query builder for PydanticModel classes.

    Usage:
        results = await (
            Query(Product)
            .filter(Product.price > 100)
            .filter(Product.status == "active")
            .order_by(Product.created_at.desc())
            .limit(10)
            .execute(db_pool, tenant_id=tenant)
        )
    """

    def __init__(self, model_class: Type[T]):
        self.model_class = model_class
        self._filters: List[FilterExpression] = []
        self._joins: List[JoinConfig] = []
        self._order_by: List[OrderByClause] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._eager_load: List[str] = []
        self._alias_counter = 1

    def filter(self, *expressions: FilterExpression) -> "Query[T]":
        """
        Add filter conditions.

        Args:
            expressions: FilterExpression objects (e.g., Product.price > 100)

        Returns:
            Self for chaining
        """
        self._filters.extend(expressions)
        return self

    def join(
        self,
        target: "Type[PydanticModel] | RelationshipProxy",
        *,
        on: str | None = None,
        type: str = "INNER",
    ) -> "Query[T]":
        """
        Add a JOIN clause.

        Args:
            target: Model class or relationship proxy to join
            on: Custom ON clause (auto-generated if not provided)
            type: JOIN type (INNER, LEFT, RIGHT)

        Returns:
            Self for chaining
        """
        from ..relationships.descriptor import RelationshipProxy

        if isinstance(target, RelationshipProxy):
            # Joining via relationship - resolve target model
            from ..relationships.registry import RelationshipRegistry
            target_model = RelationshipRegistry.resolve_model(target.config.target_model)
            if not target_model:
                raise ValueError(f"Cannot resolve model: {target.config.target_model}")

            alias = f"t{self._alias_counter}"
            self._alias_counter += 1

            self._joins.append(JoinConfig(
                target_model=target_model,
                join_type=type,
                on_clause=on,
                alias=alias,
                via_relationship=target.name,
            ))
        else:
            # Direct model join
            alias = f"t{self._alias_counter}"
            self._alias_counter += 1

            self._joins.append(JoinConfig(
                target_model=target,
                join_type=type,
                on_clause=on,
                alias=alias,
            ))

        return self

    def order_by(self, *clauses: OrderByClause) -> "Query[T]":
        """
        Add ORDER BY clauses.

        Args:
            clauses: OrderByClause objects (e.g., Product.created_at.desc())

        Returns:
            Self for chaining
        """
        self._order_by.extend(clauses)
        return self

    def limit(self, n: int) -> "Query[T]":
        """
        Set LIMIT.

        Args:
            n: Maximum number of results

        Returns:
            Self for chaining
        """
        self._limit = n
        return self

    def offset(self, n: int) -> "Query[T]":
        """
        Set OFFSET.

        Args:
            n: Number of results to skip

        Returns:
            Self for chaining
        """
        self._offset = n
        return self

    def load(self, relationship_names: List[str]) -> "Query[T]":
        """
        Eager load relationships.

        Args:
            relationship_names: Names of relationships to load

        Returns:
            Self for chaining
        """
        self._eager_load.extend(relationship_names)
        return self

    async def execute(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
    ) -> List[T]:
        """
        Execute the query and return results.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            List of model instances
        """
        from .executor import QueryExecutor

        executor = QueryExecutor(self.model_class, db_pool)
        results = await executor.execute(
            filters=self._filters,
            joins=self._joins,
            order_by=self._order_by,
            limit=self._limit,
            offset=self._offset,
            tenant_id=tenant_id,
        )

        # Eager load relationships if requested
        if self._eager_load and results:
            from ..relationships.loader import RelationshipLoader
            loader = RelationshipLoader(self.model_class)
            results = await loader.load_relationships(
                results, self._eager_load, db_pool, tenant_id
            )

        return results

    async def count(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
    ) -> int:
        """
        Execute a COUNT query.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            Count of matching records
        """
        from .executor import QueryExecutor

        executor = QueryExecutor(self.model_class, db_pool)
        return await executor.count(
            filters=self._filters,
            joins=self._joins,
            tenant_id=tenant_id,
        )

    async def first(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
    ) -> T | None:
        """
        Execute query and return first result or None.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            First matching model instance or None
        """
        results = await self.limit(1).execute(db_pool, tenant_id)
        return results[0] if results else None

    async def exists(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
    ) -> bool:
        """
        Check if any matching records exist.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            True if any records match
        """
        count = await self.count(db_pool, tenant_id)
        return count > 0
```

### 10. `src/ff_storage/query/executor.py`

```python
"""Query executor with temporal awareness."""

from typing import TYPE_CHECKING, Any, List, Type, TypeVar
from uuid import UUID

from .expressions import FilterExpression
from .ordering import OrderByClause

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel
    from ..db.pool.postgres import PostgresPool
    from .builder import JoinConfig

T = TypeVar("T", bound="PydanticModel")


class QueryExecutor:
    """
    Executes queries with temporal and multi-tenant awareness.

    Handles:
    - SCD2 temporal filtering (valid_to IS NULL)
    - Soft delete filtering (deleted_at IS NULL)
    - Multi-tenant isolation (tenant_id = ?)
    - JOIN temporal safety
    """

    def __init__(self, model_class: Type[T], db_pool: "PostgresPool"):
        self.model_class = model_class
        self.db_pool = db_pool

        # Model metadata
        self.table_name = model_class.__table_name__
        self.schema = getattr(model_class, "__schema__", "public")
        self.temporal_strategy = getattr(model_class, "__temporal_strategy__", "none")
        self.soft_delete = getattr(model_class, "__soft_delete__", True)
        self.multi_tenant = getattr(model_class, "__multi_tenant__", True)

    async def execute(
        self,
        filters: List[FilterExpression],
        joins: List["JoinConfig"],
        order_by: List[OrderByClause],
        limit: int | None,
        offset: int | None,
        tenant_id: UUID | None,
    ) -> List[T]:
        """Execute the query and return model instances."""
        sql, params = self._build_select_query(
            filters, joins, order_by, limit, offset, tenant_id
        )

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [self.model_class.model_validate(dict(row)) for row in rows]

    async def count(
        self,
        filters: List[FilterExpression],
        joins: List["JoinConfig"],
        tenant_id: UUID | None,
    ) -> int:
        """Execute a COUNT query."""
        sql, params = self._build_count_query(filters, joins, tenant_id)

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)

        return row["count"] if row else 0

    def _build_select_query(
        self,
        filters: List[FilterExpression],
        joins: List["JoinConfig"],
        order_by: List[OrderByClause],
        limit: int | None,
        offset: int | None,
        tenant_id: UUID | None,
    ) -> tuple[str, List[Any]]:
        """Build the SELECT query."""
        params: List[Any] = []
        param_index = 1

        # SELECT clause
        full_table = f"{self.schema}.{self.table_name}"
        sql = f"SELECT t0.* FROM {full_table} t0"

        # JOIN clauses
        for join in joins:
            join_sql, join_params, param_index = self._build_join(
                join, param_index, tenant_id
            )
            sql += join_sql
            params.extend(join_params)

        # WHERE clause
        where_parts = []

        # Temporal filtering for main table
        if self.temporal_strategy == "scd2":
            where_parts.append("t0.valid_to IS NULL")

        # Soft delete filtering for main table
        if self.soft_delete:
            where_parts.append("t0.deleted_at IS NULL")

        # Multi-tenant filtering
        if self.multi_tenant and tenant_id:
            where_parts.append(f"t0.tenant_id = ${param_index}")
            params.append(tenant_id)
            param_index += 1

        # User filters
        for expr in filters:
            expr_sql, expr_value, param_index = expr.to_sql(param_index)
            where_parts.append(expr_sql)
            if expr_value is not None:
                if isinstance(expr_value, (list, tuple)):
                    params.extend(expr_value)
                else:
                    params.append(expr_value)

        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        # ORDER BY clause
        if order_by:
            order_parts = [clause.to_sql() for clause in order_by]
            sql += " ORDER BY " + ", ".join(order_parts)

        # LIMIT and OFFSET
        if limit is not None:
            sql += f" LIMIT {limit}"
        if offset is not None:
            sql += f" OFFSET {offset}"

        return sql, params

    def _build_count_query(
        self,
        filters: List[FilterExpression],
        joins: List["JoinConfig"],
        tenant_id: UUID | None,
    ) -> tuple[str, List[Any]]:
        """Build a COUNT query."""
        params: List[Any] = []
        param_index = 1

        full_table = f"{self.schema}.{self.table_name}"
        sql = f"SELECT COUNT(*) as count FROM {full_table} t0"

        # JOIN clauses
        for join in joins:
            join_sql, join_params, param_index = self._build_join(
                join, param_index, tenant_id
            )
            sql += join_sql
            params.extend(join_params)

        # WHERE clause
        where_parts = []

        if self.temporal_strategy == "scd2":
            where_parts.append("t0.valid_to IS NULL")

        if self.soft_delete:
            where_parts.append("t0.deleted_at IS NULL")

        if self.multi_tenant and tenant_id:
            where_parts.append(f"t0.tenant_id = ${param_index}")
            params.append(tenant_id)
            param_index += 1

        for expr in filters:
            expr_sql, expr_value, param_index = expr.to_sql(param_index)
            where_parts.append(expr_sql)
            if expr_value is not None:
                if isinstance(expr_value, (list, tuple)):
                    params.extend(expr_value)
                else:
                    params.append(expr_value)

        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        return sql, params

    def _build_join(
        self,
        join: "JoinConfig",
        param_index: int,
        tenant_id: UUID | None,
    ) -> tuple[str, List[Any], int]:
        """
        Build a JOIN clause with temporal and tenant safety.

        CRITICAL: For SCD2 tables, JOINs must include valid_to IS NULL
        to ensure we only join to current versions.
        """
        params: List[Any] = []
        target = join.target_model
        alias = join.alias

        target_table = target.__table_name__
        target_schema = getattr(target, "__schema__", "public")
        target_temporal = getattr(target, "__temporal_strategy__", "none")
        target_soft_delete = getattr(target, "__soft_delete__", True)
        target_multi_tenant = getattr(target, "__multi_tenant__", True)

        full_target = f"{target_schema}.{target_table}"

        # Build ON clause parts
        on_parts = []

        # User-provided or auto-generated ON clause
        if join.on_clause:
            on_parts.append(join.on_clause)
        elif join.via_relationship:
            # Auto-generate from relationship
            from ..relationships.registry import RelationshipRegistry
            config = RelationshipRegistry.get_relationship(
                self.model_class.__name__, join.via_relationship
            )
            if config:
                if config.is_collection:
                    # One-to-many: target.fk = t0.id
                    fk_col = config.get_foreign_key_column()
                    on_parts.append(f"{alias}.{fk_col} = t0.id")
                else:
                    # Many-to-one: t0.fk = target.id
                    fk_col = config.get_foreign_key_column()
                    on_parts.append(f"t0.{fk_col} = {alias}.id")

        # CRITICAL: Temporal safety for joined table
        if target_temporal == "scd2":
            on_parts.append(f"{alias}.valid_to IS NULL")

        # Soft delete safety for joined table
        if target_soft_delete:
            on_parts.append(f"{alias}.deleted_at IS NULL")

        # Multi-tenant safety: ensure joined table is in same tenant
        if target_multi_tenant and self.multi_tenant and tenant_id:
            on_parts.append(f"{alias}.tenant_id = t0.tenant_id")

        on_clause = " AND ".join(on_parts) if on_parts else "TRUE"

        sql = f" {join.join_type} JOIN {full_target} {alias} ON {on_clause}"

        return sql, params, param_index
```

### 11. `src/ff_storage/query/functions.py`

```python
"""SQL functions for aggregations."""

from dataclasses import dataclass
from typing import Any


@dataclass
class AggregateFunction:
    """Represents a SQL aggregate function."""

    function_name: str
    field: str
    alias: str | None = None

    def to_sql(self, table_alias: str = "t0") -> str:
        """Convert to SQL."""
        col = f"{table_alias}.{self.field}" if self.field != "*" else "*"
        sql = f"{self.function_name}({col})"
        if self.alias:
            sql += f" AS {self.alias}"
        return sql


class FunctionFactory:
    """
    Factory for creating SQL aggregate functions.

    Usage:
        func.count(Product.id)
        func.sum(Order.total)
        func.avg(Product.price)
        func.min(Product.created_at)
        func.max(Product.created_at)
    """

    def count(self, field: Any = "*", alias: str | None = None) -> AggregateFunction:
        """COUNT aggregate."""
        field_name = self._get_field_name(field)
        return AggregateFunction("COUNT", field_name, alias)

    def sum(self, field: Any, alias: str | None = None) -> AggregateFunction:
        """SUM aggregate."""
        field_name = self._get_field_name(field)
        return AggregateFunction("SUM", field_name, alias)

    def avg(self, field: Any, alias: str | None = None) -> AggregateFunction:
        """AVG aggregate."""
        field_name = self._get_field_name(field)
        return AggregateFunction("AVG", field_name, alias)

    def min(self, field: Any, alias: str | None = None) -> AggregateFunction:
        """MIN aggregate."""
        field_name = self._get_field_name(field)
        return AggregateFunction("MIN", field_name, alias)

    def max(self, field: Any, alias: str | None = None) -> AggregateFunction:
        """MAX aggregate."""
        field_name = self._get_field_name(field)
        return AggregateFunction("MAX", field_name, alias)

    def _get_field_name(self, field: Any) -> str:
        """Extract field name from FieldProxy or string."""
        if field == "*":
            return "*"
        if hasattr(field, "field_name"):
            return field.field_name
        return str(field)


# Singleton instance
func = FunctionFactory()
```

---

## Files to Modify

### 1. `src/ff_storage/pydantic_support/base.py`

Add `__class_getitem__` to enable `Model.field` syntax:

```python
# Add this method to PydanticModel class (around line 200)

@classmethod
def __class_getitem__(cls, item: str):
    """
    Enable Model.field syntax for query expressions.

    Usage:
        Product.price > 100  # Returns FilterExpression
    """
    from ..query.expressions import FieldProxy
    return FieldProxy(item, cls)

def __init_subclass__(cls, **kwargs):
    """Called when a subclass is created."""
    super().__init_subclass__(**kwargs)

    # Initialize relationships dict
    if not hasattr(cls, "_relationships"):
        cls._relationships = {}

    # Register model with relationship registry
    from ..relationships.registry import RelationshipRegistry
    RelationshipRegistry.register_model(cls.__name__, cls)
```

Also add `__getattr__` on the metaclass or use a descriptor approach. The cleanest way is to add a custom `__getattr__` at the class level:

```python
# Add near the class definition
def __getattr__(cls, name: str):
    """Enable Model.field_name syntax for building queries."""
    # Only intercept if it's a model field
    if name.startswith("_"):
        raise AttributeError(name)

    annotations = getattr(cls, "__annotations__", {})
    if name in annotations:
        from ..query.expressions import FieldProxy
        return FieldProxy(name, cls)

    raise AttributeError(f"'{cls.__name__}' has no attribute '{name}'")
```

### 2. `src/ff_storage/__init__.py`

Add exports for new modules:

```python
# Add these exports
from .relationships import Relationship, RelationshipConfig, RelationshipRegistry
from .query import Query, FilterExpression, FieldProxy, F, OrderByClause, func

__all__ = [
    # ... existing exports ...

    # Relationships
    "Relationship",
    "RelationshipConfig",
    "RelationshipRegistry",

    # Query Builder
    "Query",
    "FilterExpression",
    "FieldProxy",
    "F",
    "OrderByClause",
    "func",
]
```

---

## Testing

### Test File: `tests/unit/test_query_expressions.py`

```python
"""Tests for query expressions."""

import pytest
from ff_storage.query.expressions import FilterExpression, FieldProxy, F


class TestFieldProxy:
    def test_equals(self):
        expr = FieldProxy("price") == 100
        assert expr.field == "price"
        assert expr.operator == "="
        assert expr.value == 100

    def test_equals_none_becomes_is_null(self):
        expr = FieldProxy("deleted_at") == None
        assert expr.operator == "IS NULL"

    def test_greater_than(self):
        expr = FieldProxy("price") > 100
        assert expr.operator == ">"
        assert expr.value == 100

    def test_contains(self):
        expr = FieldProxy("name").contains("test")
        assert expr.operator == "LIKE"
        assert expr.value == "%test%"

    def test_in_(self):
        expr = FieldProxy("status").in_(["active", "pending"])
        assert expr.operator == "IN"
        assert expr.value == ["active", "pending"]

    def test_ordering(self):
        clause = FieldProxy("created_at").desc()
        assert clause.field == "created_at"
        assert clause.direction == "DESC"


class TestFilterExpression:
    def test_to_sql_equals(self):
        expr = FilterExpression("price", "=", 100)
        sql, value, next_idx = expr.to_sql(1)
        assert sql == "t0.price = $1"
        assert value == 100
        assert next_idx == 2

    def test_to_sql_in(self):
        expr = FilterExpression("status", "IN", ["a", "b", "c"])
        sql, value, next_idx = expr.to_sql(1)
        assert sql == "t0.status IN ($1, $2, $3)"
        assert value == ["a", "b", "c"]
        assert next_idx == 4

    def test_to_sql_is_null(self):
        expr = FilterExpression("deleted_at", "IS NULL", None)
        sql, value, next_idx = expr.to_sql(1)
        assert sql == "t0.deleted_at IS NULL"
        assert value is None
        assert next_idx == 1


class TestF:
    def test_f_shorthand(self):
        expr = F.price > 100
        assert expr.field == "price"
        assert expr.operator == ">"
```

### Test File: `tests/unit/test_relationship_descriptor.py`

```python
"""Tests for relationship descriptor."""

import pytest
from typing import List
from ff_storage.relationships import Relationship, RelationshipRegistry


class TestRelationship:
    def setup_method(self):
        RelationshipRegistry.clear()

    def test_relationship_registration(self):
        class Author:
            __annotations__ = {"posts": List["Post"]}
            posts = Relationship(back_populates="author")
            posts.__set_name__(Author, "posts")

        config = RelationshipRegistry.get_relationship("Author", "posts")
        assert config is not None
        assert config.back_populates == "author"
        assert config.is_collection is True

    def test_back_reference(self):
        class Post:
            __annotations__ = {"author": "Author"}
            author = Relationship(back_populates="posts")
            author.__set_name__(Post, "author")

        config = RelationshipRegistry.get_relationship("Post", "author")
        assert config is not None
        assert config.is_collection is False
```

---

## Development Commands

```bash
# Navigate to ff-storage in the worktree
cd /Users/bgmoag/PycharmProjects/fenixflow/worktrees/ff-storage-relationships-query-builder/ff-storage

# Install dependencies
uv sync

# Run tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/unit/test_query_expressions.py -v

# Format and lint
uvx isort . && uvx ruff format . && uvx ruff check --fix .

# Type check
uv run mypy src/ff_storage/
```

---

## Implementation Order

### Phase 1: Query Builder Foundation
1. Create `src/ff_storage/query/` directory
2. Implement `expressions.py` with `FilterExpression` and `FieldProxy`
3. Implement `ordering.py` with `OrderByClause`
4. Write unit tests for expressions

### Phase 2: Query Execution
1. Implement `builder.py` with `Query` class
2. Implement `executor.py` with temporal awareness
3. Modify `pydantic_support/base.py` for `Model.field` syntax
4. Write integration tests

### Phase 3: Relationships Foundation
1. Create `src/ff_storage/relationships/` directory
2. Implement `config.py` with `RelationshipConfig`
3. Implement `registry.py` with `RelationshipRegistry`
4. Implement `descriptor.py` with `Relationship`
5. Write unit tests

### Phase 4: Relationship Loading
1. Implement `loader.py` with `RelationshipLoader`
2. Integrate with `Query.load()`
3. Write integration tests for eager loading

### Phase 5: Aggregations & Polish
1. Implement `functions.py` with `func` factory
2. Add GROUP BY support to Query
3. Update `__init__.py` exports
4. Write comprehensive tests
5. Documentation

---

## Success Criteria Checklist

- [ ] `Query(Model).filter(Model.field > value)` works
- [ ] `Query(Model).filter(Model.field.contains("text"))` works
- [ ] `Query(Model).order_by(Model.field.desc())` works
- [ ] `Query(Model).limit(10).offset(20)` works
- [ ] `Query(Model).count(db_pool)` works
- [ ] `Query(Model).first(db_pool)` returns single result or None
- [ ] `Query(Model).exists(db_pool)` returns boolean
- [ ] SCD2 queries include `valid_to IS NULL` automatically
- [ ] Soft delete queries include `deleted_at IS NULL` automatically
- [ ] Multi-tenant queries include `tenant_id = ?` automatically
- [ ] `Relationship(back_populates="...")` registers correctly
- [ ] `Query(Model).join(Model.relationship)` works
- [ ] JOINs include temporal filtering on joined tables
- [ ] JOINs include tenant isolation
- [ ] `Query(Model).load(["relationship"])` prevents N+1
- [ ] Old `repo.list(filters={...})` still works unchanged
- [ ] All tests pass
- [ ] Code is formatted and linted

---

## Reference: Existing Filter Syntax

The existing repository supports dict-based filters. Keep this working:

```python
# Current filter syntax - MUST remain working
filters = {
    "status": "active",                    # Equals
    "price": {"$gt": 100},                 # Greater than
    "price": {"$gte": 100},                # Greater than or equal
    "price": {"$lt": 100},                 # Less than
    "price": {"$lte": 100},                # Less than or equal
    "status": {"$in": ["a", "b"]},         # IN
    "status": {"$nin": ["x", "y"]},        # NOT IN
    "name": {"$like": "%test%"},           # LIKE
    "name": {"$ilike": "%test%"},          # ILIKE
    "deleted_at": {"$null": True},         # IS NULL
    "deleted_at": {"$null": False},        # IS NOT NULL
}
```

The new Query builder is an alternative, more fluent API - not a replacement.