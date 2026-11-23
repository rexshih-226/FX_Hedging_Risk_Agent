"""Shared contract validation and canonical identifiers."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return sha256(raw.encode()).hexdigest()


def parse_time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result


def validate(name, value):
    resources = []
    for path in (ROOT / "schemas").glob("*.json"):
        schema = read_json(path)
        resources.append((schema["$id"], Resource.from_contents(schema)))
    schema = read_json(ROOT / "schemas" / f"{name}.json")
    validator = Draft202012Validator(schema, registry=Registry().with_resources(resources), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        raise ValueError("; ".join(f"{'/'.join(map(str, e.path)) or '$'}: {e.message}" for e in errors))
