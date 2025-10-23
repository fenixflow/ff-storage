"""
Query builder module for database-agnostic SQL generation.

Provides QueryBuilder base class and database-specific implementations.
"""

from .base import QueryBuilder
from .postgres import PostgresQueryBuilder

__all__ = ["QueryBuilder", "PostgresQueryBuilder"]
