"""Turns a DGT ``Test-num-NNN.shtml`` page into an :class:`Exam`."""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urljoin

from lxml import html as lxml_html
from lxml.html import HtmlElement

from dgt_scraper.models import Answer, Exam, Question

__all__ = ["ParseError", "parse_exam"]

_TITLE_XPATH: Final = '//h3[contains(@class,"tit_general")]'
_QUESTION_XPATH: Final = (
    '//article[contains(concat(" ",normalize-space(@class)," ")," test ")]'
)
_QUESTION_TITLE_XPATH: Final = './/h4[contains(@class,"tit_not")]'
_ANSWER_XPATH: Final = './section[contains(@class,"content_test")]/ul/li'
_ANSWER_LETTER_XPATH: Final = './span[contains(@class,"opcion")]'
_CORRECT_XPATH: Final = (
    './/div[contains(@class,"content_respuesta")]'
    '//span[contains(@class,"opcion")]'
)
_IMAGE_XPATH: Final = ".//figure//img"

_QUESTION_NUMBER_PREFIX: Final = re.compile(r"^\d+\s*[.)–-]\s*")


class ParseError(Exception):
    """The page did not look like a DGT exam, most likely upstream markup changed."""

    def __init__(self, exam_number: int, reason: str) -> None:
        super().__init__(f"exam {exam_number}: {reason}")
        self.exam_number = exam_number
        self.reason = reason


def _elements(node: HtmlElement, xpath: str) -> list[HtmlElement]:
    """Run ``xpath`` and keep only the element results."""
    found = node.xpath(xpath)
    if not isinstance(found, list):
        return []
    return [item for item in found if isinstance(item, HtmlElement)]


def _text(node: HtmlElement) -> str:
    """Collapsed text of ``node`` and all its descendants."""
    return " ".join("".join(node.itertext()).split())


def _attr(node: HtmlElement, name: str) -> str | None:
    value = node.get(name)
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _letter(node: HtmlElement) -> str | None:
    """The ``A``/``B``/``C`` marker of an answer or of the answer box, without punctuation."""
    marker = _elements(node, _ANSWER_LETTER_XPATH)
    source = marker[0] if marker else node
    letter = _text(source).strip().rstrip(".)").strip()
    return letter.upper() or None


def _parse_question(
    exam_number: int, number: int, article: HtmlElement, base_url: str
) -> Question:
    titles = _elements(article, _QUESTION_TITLE_XPATH)
    if not titles:
        raise ParseError(exam_number, f"question {number} has no title")
    title = _QUESTION_NUMBER_PREFIX.sub("", _text(titles[0]))
    if not title:
        raise ParseError(exam_number, f"question {number} has an empty title")

    answer_nodes = _elements(article, _ANSWER_XPATH)
    if not answer_nodes:
        raise ParseError(exam_number, f"question {number} has no answers")

    correct_nodes = _elements(article, _CORRECT_XPATH)
    if not correct_nodes:
        raise ParseError(exam_number, f"question {number} has no correct answer")
    correct_letter = _letter(correct_nodes[0])
    if correct_letter is None:
        raise ParseError(exam_number, f"question {number} has an unreadable correct answer")

    answers: list[Answer] = []
    for node in answer_nodes:
        letter = _letter(node)
        text = _text(node)
        if letter is not None and text.upper().startswith(f"{letter}."):
            text = text[len(letter) + 1 :].lstrip()
        if not text:
            raise ParseError(exam_number, f"question {number} has an empty answer")
        answers.append(Answer(text=text, correct=letter == correct_letter))

    marked = sum(answer.correct for answer in answers)
    if marked != 1:
        raise ParseError(
            exam_number,
            f"question {number}: correct answer {correct_letter!r} matched "
            f"{marked} of {len(answers)} answers",
        )

    images = _elements(article, _IMAGE_XPATH)
    image_source: str | None = None
    image_alt: str | None = None
    if images:
        src = _attr(images[0], "src")
        if src is not None:
            image_source = urljoin(base_url, src)
            image_alt = _attr(images[0], "alt")

    return Question(
        number=number,
        title=title,
        answers=tuple(answers),
        image_source=image_source,
        image_alt=image_alt,
    )


def parse_exam(content: bytes, exam_number: int, url: str) -> Exam:
    """Parse the HTML of one exam page.

    Raises:
        ParseError: the page is missing the title, the questions, or an answer.
    """
    root = lxml_html.fromstring(content)
    if not isinstance(root, HtmlElement):
        raise ParseError(exam_number, "page is not HTML")

    titles = _elements(root, _TITLE_XPATH)
    if not titles:
        raise ParseError(exam_number, "no h3.tit_general title")
    title = _text(titles[0])
    if not title:
        raise ParseError(exam_number, "empty h3.tit_general title")

    articles = _elements(root, _QUESTION_XPATH)
    if not articles:
        raise ParseError(exam_number, "no article.test questions")

    questions = tuple(
        _parse_question(exam_number, number, article, url)
        for number, article in enumerate(articles, start=1)
    )
    return Exam(number=exam_number, title=title, url=url, questions=questions)
