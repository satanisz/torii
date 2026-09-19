"""Strict decoding before schema validation; called after resource authorization."""

import json
import math
from decimal import Decimal, DecimalException
from typing import NoReturn

from torii_api.domain.errors import DomainError

MAX_BODY = 256 * 1024
MAX_DEPTH = 32


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("Non-JSON numeric constant")


def _number(value: str) -> int:
    # Preserve the exact mathematical value before an IEEE-754 conversion can round it.
    if not math.isfinite(float(value)):
        raise ValueError("Nonfinite numeric value")
    precise = Decimal(value)
    if precise != precise.to_integral_value() or abs(precise) > 2**53 - 1:
        raise DomainError(422, "validation_failed")
    return int(precise)


def decode_json(body: bytes, content_type: str | None) -> object:
    if len(body) > MAX_BODY:
        raise DomainError(413, "payload_too_large")
    parts = (content_type or "").lower().replace(" ", "").split(";")
    if parts[0] != "application/json" or any(
        item not in ("charset=utf-8", 'charset="utf-8"') for item in parts[1:]
    ):
        raise DomainError(415, "unsupported_media_type")
    try:
        result: object = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=_number,
            parse_int=_number,
        )
        stack = [(result, 0)]
        while stack:
            value, parent_depth = stack.pop()
            if isinstance(value, dict | list):
                depth = parent_depth + 1
                if depth > MAX_DEPTH:
                    raise DomainError(413, "payload_too_deep")
                if isinstance(value, dict):
                    stack.extend((key, depth) for key in value)
                    stack.extend((item, depth) for item in value.values())
                else:
                    stack.extend((item, depth) for item in value)
            elif isinstance(value, str):
                value.encode("utf-8", errors="strict")
                if "\x00" in value:
                    raise DomainError(422, "validation_failed")
        return result
    except RecursionError as exc:
        raise DomainError(413, "payload_too_deep") from exc
    except (ValueError, UnicodeError, DecimalException) as exc:
        raise DomainError(400, "invalid_json") from exc
