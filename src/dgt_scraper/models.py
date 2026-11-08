"""Domain model and the JSON shapes written to ``dist/``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

__all__ = [
    "Answer",
    "AnswerJson",
    "Exam",
    "ExamJson",
    "ManifestEntryJson",
    "ManifestJson",
    "Question",
    "QuestionJson",
]


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


class ExamJson(TypedDict):
    number: int
    title: str
    url: str
    scraped_at: str
    questions: list[QuestionJson]


class ManifestEntryJson(TypedDict):
    number: int
    title: str
    path: str


class ManifestJson(TypedDict):
    generated_at: str
    source: str
    exams: list[ManifestEntryJson]
