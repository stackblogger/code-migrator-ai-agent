"""Shared words for validation rules and column types, used by every framework adapter."""

# How a "numeric string" (class-validator @IsNumberString) is written in Pydantic.
NUMERIC_STRING_PATTERN = r"^-?\d+(\.\d+)?$"

# Canonical column types: integer, bigint, float, numeric(p,s), varchar(n), text,
# boolean, timestamp, date, uuid, json. Unknown types keep their original name.
