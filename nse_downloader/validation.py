import json
import logging
import math
from datetime import date
from decimal import Decimal, InvalidOperation

log = logging.getLogger(__name__)


class ValidationError(ValueError):
    pass


def at_path(value, path):
    for key in path.split(".") if path else []:
        if not isinstance(value, dict) or key not in value:
            raise ValidationError(f"Missing response path: {path}")
        value = value[key]
    return value


def validate_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Expected ISO date, got {value!r}") from exc


def normalize(payload, source, spec, dataset):
    records = at_path(payload, source.get("records_path", "data"))
    if not isinstance(records, list) or not records:
        raise ValidationError("Expected a non-empty list of records")
    trading_date = validate_date(at_path(payload, source["date_path"]))
    rows = []
    for record in records:
        if not isinstance(record, dict):
            raise ValidationError("Record is not an object")
        row = {}
        for column, source_key in spec["columns"].items():
            if source_key not in record:
                raise ValidationError(f"Missing column: {source_key}")
            value = record[source_key]
            if value is None or isinstance(value, (dict, list, bool)) or str(value).strip() in ("", "-", "NA"):
                raise ValidationError(f"Invalid required value: {column}")
            if column in spec.get("numeric", []):
                try:
                    number = Decimal(str(value).replace(",", "").strip())
                    if not number.is_finite():
                        raise InvalidOperation()
                    if column in spec.get("nonnegative", []) and number < 0:
                        raise InvalidOperation()
                    value = format(number, "f")
                except InvalidOperation as exc:
                    raise ValidationError(f"Invalid numeric value: {column}={value!r}") from exc
            else:
                value = str(value).strip()
            row[column] = value
        row.update(dataset=dataset, trading_date=trading_date, category=source.get("category", ""))
        rows.append(row)
    return rows, trading_date


def deduplicate(rows, keys):
    unique = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in unique and unique[key] != row:
            raise ValidationError(f"Conflicting duplicate for {key!r}; refusing silent data loss")
        unique[key] = row
    log.info("duplicates_removed=%d", len(rows) - len(unique))
    return [unique[key] for key in sorted(unique)]
