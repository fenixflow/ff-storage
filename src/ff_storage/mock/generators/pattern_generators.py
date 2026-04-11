"""Pattern-based value generators for mock data.

This module provides generators that create values based on field name patterns.
Patterns are matched using regex and produce realistic values for common field types.

Pattern priority:
1. Explicit mock_pattern from Field()
2. Field name regex matching
"""

from __future__ import annotations

import re
from datetime import timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from faker import Faker

    from .registry import FieldMeta


# Type alias for generator functions
GeneratorFunc = Callable[["Faker", "FieldMeta"], Any]


def gen_email(faker: Faker, meta: FieldMeta) -> str:
    """Generate an email address."""
    return faker.email()


def gen_first_name(faker: Faker, meta: FieldMeta) -> str:
    """Generate a first name."""
    return faker.first_name()


def gen_last_name(faker: Faker, meta: FieldMeta) -> str:
    """Generate a last name."""
    return faker.last_name()


def gen_name(faker: Faker, meta: FieldMeta) -> str:
    """Generate a full name."""
    return faker.name()


def gen_username(faker: Faker, meta: FieldMeta) -> str:
    """Generate a username."""
    return faker.user_name()


def gen_company(faker: Faker, meta: FieldMeta) -> str:
    """Generate a company name."""
    return faker.company()


def gen_phone(faker: Faker, meta: FieldMeta) -> str:
    """Generate a phone number."""
    return faker.phone_number()


def gen_url(faker: Faker, meta: FieldMeta) -> str:
    """Generate a URL."""
    return faker.url()


def gen_address(faker: Faker, meta: FieldMeta) -> str:
    """Generate a street address."""
    return faker.street_address()


def gen_city(faker: Faker, meta: FieldMeta) -> str:
    """Generate a city name."""
    return faker.city()


def gen_state(faker: Faker, meta: FieldMeta) -> str:
    """Generate a state/province."""
    return faker.state()


def gen_country(faker: Faker, meta: FieldMeta) -> str:
    """Generate a country name."""
    return faker.country()


def gen_postal_code(faker: Faker, meta: FieldMeta) -> str:
    """Generate a postal/zip code."""
    return faker.postcode()


def gen_latitude(faker: Faker, meta: FieldMeta) -> float:
    """Generate a latitude."""
    return float(faker.latitude())


def gen_longitude(faker: Faker, meta: FieldMeta) -> float:
    """Generate a longitude."""
    return float(faker.longitude())


def gen_datetime(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a datetime within the past year."""
    dt = faker.date_time_between(start_date="-1y", end_date="now")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def gen_future_datetime(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a future datetime (within next year)."""
    dt = faker.date_time_between(start_date="now", end_date="+1y")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def gen_date(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a date within the past year."""
    return faker.date_between(start_date="-1y", end_date="today")


def gen_future_date(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a future date (within next 6 months)."""
    return faker.date_between(start_date="today", end_date="+6M")


def gen_far_future_date(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a date far in the future (6-18 months)."""
    return faker.date_between(start_date="+6M", end_date="+18M")


def gen_birth_date(faker: Faker, meta: FieldMeta) -> Any:
    """Generate a birth date (18-80 years old)."""
    return faker.date_of_birth(minimum_age=18, maximum_age=80)


def gen_money_amount(faker: Faker, meta: FieldMeta) -> Decimal:
    """Generate a monetary amount."""
    scale = meta.scale or 2

    min_val = float(meta.ge) if meta.ge is not None else 1.0
    max_val = float(meta.le) if meta.le is not None else 10_000_000.0

    value = faker.pyfloat(min_value=min_val, max_value=max_val)
    quantize_str = "0." + "0" * scale
    return Decimal(str(value)).quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


def gen_currency(faker: Faker, meta: FieldMeta) -> str:
    """Generate a currency code."""
    return faker.currency_code()


def gen_percentage(faker: Faker, meta: FieldMeta) -> Decimal:
    """Generate a percentage (0-100)."""
    min_val = float(meta.ge) if meta.ge is not None else 0.0
    max_val = float(meta.le) if meta.le is not None else 100.0

    value = faker.pyfloat(min_value=min_val, max_value=max_val)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gen_boolean(faker: Faker, meta: FieldMeta) -> bool:
    """Generate a boolean."""
    return faker.boolean()


def gen_integer(faker: Faker, meta: FieldMeta) -> int:
    """Generate an integer."""
    min_val = int(meta.ge) if meta.ge is not None else 0
    max_val = int(meta.le) if meta.le is not None else 1000
    return faker.random_int(min=min_val, max=max_val)


def gen_small_integer(faker: Faker, meta: FieldMeta) -> int:
    """Generate a small integer (1-10)."""
    return faker.random_int(min=1, max=10)


def gen_title(faker: Faker, meta: FieldMeta) -> str:
    """Generate a title."""
    max_len = meta.max_length or 255
    title = faker.sentence(nb_words=5).rstrip(".")
    return title[:max_len] if len(title) > max_len else title


def gen_description(faker: Faker, meta: FieldMeta) -> str:
    """Generate a description/paragraph."""
    max_len = meta.max_length or 1000
    text = faker.paragraph(nb_sentences=3)
    return text[:max_len] if len(text) > max_len else text


def gen_text(faker: Faker, meta: FieldMeta) -> str:
    """Generate multi-paragraph text."""
    max_len = meta.max_length or 5000
    text = "\n\n".join(faker.paragraphs(nb=3))
    return text[:max_len] if len(text) > max_len else text


def gen_code(faker: Faker, meta: FieldMeta) -> str:
    """Generate a code/reference string."""
    return faker.bothify("???-###").upper()


def gen_sku(faker: Faker, meta: FieldMeta) -> str:
    """Generate a SKU."""
    return faker.bothify("SKU-#####")


# Default pattern generators
# Order matters - more specific patterns should come first
# Format: (regex_pattern, generator_function)
DEFAULT_NAME_PATTERNS: list[tuple[str, GeneratorFunc]] = [
    # Email patterns
    (r"^email$|_email$", gen_email),
    # Name patterns
    (r"^first_name$|_first_name$", gen_first_name),
    (r"^last_name$|_last_name$", gen_last_name),
    (r"^username$|_username$", gen_username),
    (r"_name$|^name$", gen_name),
    (r"^company$|_company$|^organization$", gen_company),
    # Contact
    (r"^phone$|_phone$|^mobile$|^telephone$", gen_phone),
    (r"^website$|^url$|_url$|^link$", gen_url),
    # Address
    (r"^address$|_address$|^street$", gen_address),
    (r"^city$|_city$", gen_city),
    (r"^state$|_state$|^province$|^state_province$", gen_state),
    (r"^country$|_country$|^nation$", gen_country),
    (r"^postal_code$|^postcode$|^zip$|_zip$|^zipcode$", gen_postal_code),
    # Geo
    (r"^latitude$|^lat$", gen_latitude),
    (r"^longitude$|^lng$|^lon$", gen_longitude),
    # Date/datetime patterns
    (r"_at$|_datetime$", gen_datetime),
    (r"^inception_date$|^start_date$|^begin_date$", gen_future_date),
    (r"^expiry_date$|^end_date$|^expiration_date$", gen_far_future_date),
    (r"^birth_date$|^date_of_birth$|^dob$", gen_birth_date),
    (r"_date$", gen_date),
    # Financial patterns
    (r"_amount$|_value$|^total$|_total$|_price$|^price$", gen_money_amount),
    (r"^currency$|_currency$", gen_currency),
    (r"_pct$|_percentage$|_percent$|_rate$", gen_percentage),
    # Boolean patterns
    (r"^is_|^has_|^can_|^should_|^allow_", gen_boolean),
    # Number patterns
    (r"_number$|_count$|_qty$|_quantity$", gen_integer),
    # Text patterns
    (r"^title$|_title$|^subject$", gen_title),
    (r"^description$|_description$|^notes$|^comment$|^summary$", gen_description),
    (r"^content$|^body$|_content$|_body$", gen_text),
    # Code patterns
    (r"^code$|_code$|^reference$|_reference$|^ref$", gen_code),
    (r"^sku$|_sku$", gen_sku),
]

# Compile patterns for efficiency
COMPILED_PATTERNS: list[tuple[re.Pattern, GeneratorFunc]] = [
    (re.compile(pattern, re.IGNORECASE), func) for pattern, func in DEFAULT_NAME_PATTERNS
]

# Named patterns for explicit mock_pattern usage
NAMED_PATTERNS: dict[str, GeneratorFunc] = {
    "email": gen_email,
    "first_name": gen_first_name,
    "last_name": gen_last_name,
    "name": gen_name,
    "username": gen_username,
    "company": gen_company,
    "phone": gen_phone,
    "url": gen_url,
    "address": gen_address,
    "city": gen_city,
    "state": gen_state,
    "country": gen_country,
    "postal_code": gen_postal_code,
    "latitude": gen_latitude,
    "longitude": gen_longitude,
    "datetime": gen_datetime,
    "future_datetime": gen_future_datetime,
    "date": gen_date,
    "future_date": gen_future_date,
    "birth_date": gen_birth_date,
    "money": gen_money_amount,
    "amount": gen_money_amount,
    "currency": gen_currency,
    "percentage": gen_percentage,
    "percent": gen_percentage,
    "boolean": gen_boolean,
    "bool": gen_boolean,
    "integer": gen_integer,
    "number": gen_integer,
    "title": gen_title,
    "description": gen_description,
    "text": gen_text,
    "code": gen_code,
    "sku": gen_sku,
}


def get_pattern_generator(field_name: str) -> GeneratorFunc | None:
    """Find a generator based on field name pattern matching.

    Args:
        field_name: The name of the field to match

    Returns:
        Generator function or None if no pattern matches
    """
    for pattern, func in COMPILED_PATTERNS:
        if pattern.search(field_name):
            return func
    return None


def get_named_pattern_generator(pattern_name: str) -> GeneratorFunc | None:
    """Get generator for an explicit named pattern (from mock_pattern).

    Args:
        pattern_name: The pattern name (e.g., "email", "name")

    Returns:
        Generator function or None if pattern name not found
    """
    return NAMED_PATTERNS.get(pattern_name.lower())
