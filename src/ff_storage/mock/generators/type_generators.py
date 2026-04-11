"""Type-based value generators for mock data.

This module provides generators that create values based on Python types,
respecting field constraints like max_length, ge/le bounds, and precision.

These are the fallback generators used when no pattern match is found.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from faker import Faker

    from .registry import FieldMeta


def generate_uuid(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a UUID."""
    return uuid4()


def generate_string(faker: Faker, meta: FieldMeta) -> str:
    """Generate a string respecting max_length constraint."""
    max_len = meta.max_length or 50
    # Generate text that fits within max_length
    if max_len <= 10:
        return faker.pystr(max_chars=max_len)
    elif max_len <= 50:
        return faker.pystr(max_chars=min(max_len, 20))
    else:
        text = faker.sentence(nb_words=5)
        return text[:max_len] if len(text) > max_len else text


def generate_int(faker: Faker, meta: FieldMeta) -> int:
    """Generate an integer respecting ge/le/gt/lt constraints."""
    min_val = 0
    max_val = 1000

    if meta.ge is not None:
        min_val = int(meta.ge)
    elif meta.gt is not None:
        min_val = int(meta.gt) + 1

    if meta.le is not None:
        max_val = int(meta.le)
    elif meta.lt is not None:
        max_val = int(meta.lt) - 1

    # Ensure valid range
    if min_val > max_val:
        min_val, max_val = max_val, min_val

    return faker.random_int(min=min_val, max=max_val)


def generate_float(faker: Faker, meta: FieldMeta) -> float:
    """Generate a float respecting ge/le/gt/lt constraints."""
    min_val = 0.0
    max_val = 1000.0

    if meta.ge is not None:
        min_val = float(meta.ge)
    elif meta.gt is not None:
        min_val = float(meta.gt) + 0.01

    if meta.le is not None:
        max_val = float(meta.le)
    elif meta.lt is not None:
        max_val = float(meta.lt) - 0.01

    # Ensure valid range
    if min_val > max_val:
        min_val, max_val = max_val, min_val

    return faker.pyfloat(min_value=min_val, max_value=max_val)


def generate_decimal(faker: Faker, meta: FieldMeta) -> Decimal:
    """Generate a Decimal respecting precision, scale, and bounds."""
    precision = meta.precision or 15
    scale = meta.scale or 2

    # Calculate reasonable bounds based on precision
    max_whole_digits = precision - scale
    default_max = min(10**max_whole_digits - 1, 10_000_000)  # Cap at 10M

    min_val = 0.0
    max_val = float(default_max)

    if meta.ge is not None:
        min_val = float(meta.ge)
    elif meta.gt is not None:
        min_val = float(meta.gt) + (10**-scale)

    if meta.le is not None:
        max_val = float(meta.le)
    elif meta.lt is not None:
        max_val = float(meta.lt) - (10**-scale)

    # Ensure valid range
    if min_val > max_val:
        min_val, max_val = max_val, min_val

    value = faker.pyfloat(min_value=min_val, max_value=max_val)
    quantize_str = "0." + "0" * scale
    return Decimal(str(value)).quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


def generate_bool(faker: Faker, meta: FieldMeta) -> bool:
    """Generate a boolean."""
    return faker.boolean()


def generate_datetime(faker: Faker, meta: FieldMeta) -> datetime:
    """Generate a datetime in UTC within the past year."""
    dt = faker.date_time_between(start_date="-1y", end_date="now")
    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def generate_date(faker: Faker, meta: FieldMeta) -> date:
    """Generate a date within the past year."""
    return faker.date_between(start_date="-1y", end_date="today")


def generate_time(faker: Faker, meta: FieldMeta) -> time:
    """Generate a time."""
    return faker.time_object()


def generate_timedelta(faker: Faker, meta: FieldMeta) -> timedelta:
    """Generate a timedelta (random duration up to 30 days)."""
    seconds = faker.random_int(min=0, max=30 * 24 * 60 * 60)
    return timedelta(seconds=seconds)


def generate_bytes(faker: Faker, meta: FieldMeta) -> bytes:
    """Generate random bytes."""
    length = meta.max_length or 32
    return faker.binary(length=min(length, 256))


def generate_list(faker: Faker, meta: FieldMeta) -> list:
    """Generate an empty list (complex lists need custom generators)."""
    return []


def generate_dict(faker: Faker, meta: FieldMeta) -> dict:
    """Generate an empty dict (complex dicts need custom generators)."""
    return {}


def generate_enum(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a random enum value."""
    if meta.enum_class and meta.enum_values:
        return random.choice(meta.enum_values)
    return None


# Type name to generator mapping
TYPE_GENERATORS: dict[str, Any] = {
    "uuid": generate_uuid,
    "str": generate_string,
    "string": generate_string,
    "int": generate_int,
    "integer": generate_int,
    "float": generate_float,
    "number": generate_float,
    "decimal": generate_decimal,
    "bool": generate_bool,
    "boolean": generate_bool,
    "datetime": generate_datetime,
    "date": generate_date,
    "time": generate_time,
    "timedelta": generate_timedelta,
    "bytes": generate_bytes,
    "list": generate_list,
    "dict": generate_dict,
    "enum": generate_enum,
}


def get_type_generator(type_name: str) -> Any | None:
    """Get generator function for a type name.

    Args:
        type_name: Lowercase type name (e.g., "uuid", "str", "decimal")

    Returns:
        Generator function or None if not found
    """
    return TYPE_GENERATORS.get(type_name.lower())
