"""Write exams into the ``dist/`` folder."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlparse

from dgt_scraper.fetch import BASE_URL, Fetcher
from dgt_scraper.models import (
    AnswerJson,
    Exam,
    ExamJson,
    ManifestEntryJson,
    ManifestJson,
    QuestionJson,
)

__all__ = [
    "MANIFEST_NAME",
    "exam_dir",
    "manifest_numbers",
    "read_exam_json",
    "write_exam",
    "write_manifest",
]

MANIFEST_NAME: Final = "manifest.json"
EXAM_JSON_NAME: Final = "index.json"
_EXAM_DIR_PATTERN: Final = re.compile(r"^exam-(\d+)$")
_DEFAULT_IMAGE_SUFFIX: Final = ".jpg"
_IMAGE_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"})


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dump(path: Path, payload: ExamJson | ManifestJson) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    path.write_text(f"{text}\n", encoding="utf-8")


def _load(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _keep_timestamp(path: Path, payload: dict[str, object], field: str) -> None:
    """Reuse the stored timestamp when nothing else in the file changed."""
    previous = _load(path)
    if previous is None:
        return
    stored = previous.get(field)
    if not isinstance(stored, str):
        return
    if {**previous, field: None} == {**payload, field: None}:
        payload[field] = stored


def exam_dir(out_dir: Path, number: int) -> Path:
    return out_dir / f"exam-{number}"


def _image_suffix(url: str) -> str:
    """Extension for a downloaded image, taken from the URL path."""
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in _IMAGE_SUFFIXES else _DEFAULT_IMAGE_SUFFIX


async def write_exam(exam: Exam, out_dir: Path, fetcher: Fetcher) -> Path:
    """Write one exam's JSON and images, returning the exam directory."""
    target = exam_dir(out_dir, exam.number)
    questions: list[QuestionJson] = []

    for question in exam.questions:
        image_name: str | None = None
        image_alt: str | None = None
        if question.image_source is not None:
            candidate = f"image-{question.number}{_image_suffix(question.image_source)}"
            if await fetcher.image(question.image_source, target / candidate):
                image_name = candidate
                image_alt = question.image_alt

        answers: list[AnswerJson] = [
            {"text": answer.text, "correct": answer.correct}
            for answer in question.answers
        ]
        questions.append(
            {
                "number": question.number,
                "title": question.title,
                "image": image_name,
                "image_alt": image_alt,
                "image_source": question.image_source,
                "answers": answers,
            }
        )

    payload: ExamJson = {
        "number": exam.number,
        "title": exam.title,
        "url": exam.url,
        "scraped_at": _now(),
        "questions": questions,
    }
    path = target / EXAM_JSON_NAME
    _keep_timestamp(path, cast(dict[str, object], payload), "scraped_at")
    _dump(path, payload)
    return target


def read_exam_json(out_dir: Path, number: int) -> ExamJson | None:
    """Load a previously written exam, or ``None`` if it is not in ``out_dir``."""
    path = exam_dir(out_dir, number) / EXAM_JSON_NAME
    if not path.is_file():
        return None
    return cast(ExamJson, json.loads(path.read_text(encoding="utf-8")))


def manifest_numbers(out_dir: Path) -> list[int]:
    """Exam numbers already present in ``out_dir``, ascending."""
    numbers: list[int] = []
    for child in out_dir.glob("exam-*"):
        match = _EXAM_DIR_PATTERN.match(child.name)
        if match is not None and (child / EXAM_JSON_NAME).is_file():
            numbers.append(int(match.group(1)))
    return sorted(numbers)


def write_manifest(out_dir: Path) -> ManifestJson:
    """Rebuild ``manifest.json`` from whatever exams are on disk."""
    entries: list[ManifestEntryJson] = []
    for number in sorted(manifest_numbers(out_dir), reverse=True):
        exam = read_exam_json(out_dir, number)
        if exam is None:
            continue
        entries.append(
            {
                "number": exam["number"],
                "title": exam["title"],
                "path": f"exam-{number}/{EXAM_JSON_NAME}",
            }
        )

    manifest: ManifestJson = {
        "generated_at": _now(),
        "source": f"{BASE_URL}/",
        "exams": entries,
    }
    path = out_dir / MANIFEST_NAME
    _keep_timestamp(path, cast(dict[str, object], manifest), "generated_at")
    _dump(path, manifest)
    return manifest
