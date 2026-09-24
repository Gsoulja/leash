"""Structural validation of live events against the official schema
(data/schemas/authorization_event.schema.json). It only rejects; it never changes a value. The translator
receives it as a plain callable, so the translator itself reads no files."""

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from leash.adapters.viseca_api.translate import InvalidEvent


def load_event_validator(schema_path: Path) -> Callable[[Mapping[str, Any]], None]:
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")),
                                     format_checker=FormatChecker())

    def validate(event: Mapping[str, Any]) -> None:
        errors = sorted(validator.iter_errors(event), key=lambda e: list(e.absolute_path))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.absolute_path) or "(event)"
            authorization = event.get("authorization") if isinstance(event, Mapping) else None
            live_id = authorization.get("authorization_id") if isinstance(authorization, Mapping) else None
            raise InvalidEvent(f"{where}: {first.message}", live_id if isinstance(live_id, str) and live_id else None)

    return validate
