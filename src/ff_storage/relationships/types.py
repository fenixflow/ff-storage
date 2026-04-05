"""Relationship type definitions.

This module provides the RelationType enum for classifying relationships.
"""

from enum import Enum


class RelationType(Enum):
    """
    Enum representing the type of relationship between models.

    Attributes:
        ONE_TO_ONE: A single record relates to exactly one other record
        ONE_TO_MANY: A single record relates to multiple other records
        MANY_TO_ONE: Multiple records relate to a single other record
        MANY_TO_MANY: Multiple records relate to multiple other records (via junction table)
    """

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"
