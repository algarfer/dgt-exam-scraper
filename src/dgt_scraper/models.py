"""Domain model and the JSON shapes written to ``dist/``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, TypedDict

__all__ = [
    "EXAM_SCHEMA_URL",
    "MANIFEST_SCHEMA_URL",
    "SCHEMA_BASE_URL",
    "Answer",
    "AnswerJson",
    "Exam",
    "ExamJson",
    "ManifestEntryJson",
    "ManifestJson",
    "Question",
    "QuestionJson",
]

SCHEMA_BASE_URL: Final = (
    "https://raw.githubusercontent.com/algarfer/dgt-exam-scraper/master/schemas"
)
EXAM_SCHEMA_URL: Final = f"{SCHEMA_BASE_URL}/exam.schema.json"
MANIFEST_SCHEMA_URL: Final = f"{SCHEMA_BASE_URL}/manifest.schema.json"


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    correct: bool


@dataclass(frozen=True, slots=True)
class Question:
    number: int
    title: str
    answers: tuple[Answer, ...]
    image_source: str | None
    image_alt: str | None


@dataclass(frozen=True, slots=True)
class Exam:
    number: int
    title: str
    url: str
    questions: tuple[Question, ...]


class AnswerJson(TypedDict):
    text: str
    correct: bool


class QuestionJson(TypedDict):
    number: int
    title: str
    image: str | None
    image_alt: str | None
    image_source: str | None
    answers: list[AnswerJson]


# Functional syntax: "$schema" is not a valid Python identifier.
ExamJson = TypedDict(
    "ExamJson",
    {
        "$schema": str,
        "number": int,
        "title": str,
        "url": str,
        "scraped_at": str,
        "questions": list[QuestionJson],
    },
)


class ManifestEntryJson(TypedDict):
    number: int
    title: str
    path: str


ManifestJson = TypedDict(
    "ManifestJson",
    {
        "$schema": str,
        "generated_at": str,
        "source": str,
        "exams": list[ManifestEntryJson],
    },
)
