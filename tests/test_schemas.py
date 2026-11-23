"""Validates everything in ``dist/`` against the schemas in ``schemas/``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest
from jsonschema import Draft202012Validator

from dgt_scraper.models import EXAM_SCHEMA_URL, MANIFEST_SCHEMA_URL

ROOT: Final = Path(__file__).resolve().parent.parent
DIST: Final = ROOT / "dist"
SCHEMAS: Final = ROOT / "schemas"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _json(SCHEMAS / name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _exam_paths() -> list[Path]:
    return sorted(DIST.glob("exam-*/index.json"))


def _check(validator: Draft202012Validator, instance: Any, where: Path) -> None:
    errors = sorted(validator.iter_errors(instance), key=lambda error: error.json_path)
    assert not errors, "\n".join(
        f"{where.relative_to(ROOT)}: {error.json_path}: {error.message}"
        for error in errors
    )


def test_schema_ids_match_the_urls_the_generators_write() -> None:
    assert _json(SCHEMAS / "exam.schema.json")["$id"] == EXAM_SCHEMA_URL
    assert _json(SCHEMAS / "manifest.schema.json")["$id"] == MANIFEST_SCHEMA_URL


def test_manifest_matches_its_schema() -> None:
    path = DIST / "manifest.json"
    if not path.is_file():
        pytest.skip(f"no {path}; run `dgt-scraper scrape` first")
    manifest = _json(path)
    _check(_validator("manifest.schema.json"), manifest, path)
    assert manifest["$schema"] == MANIFEST_SCHEMA_URL


def test_every_exam_matches_its_schema() -> None:
    paths = _exam_paths()
    if not paths:
        pytest.skip(f"no exams in {DIST}; run `dgt-scraper scrape` first")
    validator = _validator("exam.schema.json")
    for path in paths:
        exam = _json(path)
        _check(validator, exam, path)
        assert exam["$schema"] == EXAM_SCHEMA_URL

