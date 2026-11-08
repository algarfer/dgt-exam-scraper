"""Canary: does revista.dgt.es still produce the data we committed?

Picks a random exam out of ``dist/``, fetches that page again, re-parses it and compares
the result with the stored JSON. If DGT changes their markup the XPath stops matching or
the extracted text drifts, and this fails instead of silently writing worse data on the
next scheduled run.

Set ``DGT_EXAM_NUMBER`` to re-run against one specific exam after a failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from pathlib import Path
from typing import Final

import httpx
import pytest

from dgt_scraper.fetch import Fetcher
from dgt_scraper.models import Exam, ExamJson, ManifestJson
from dgt_scraper.parser import parse_exam

DIST: Final = Path(__file__).resolve().parent.parent / "dist"
MANIFEST: Final = DIST / "manifest.json"


def _pick_exam_number() -> int:
    override = os.environ.get("DGT_EXAM_NUMBER")
    if override:
        return int(override)

    if not MANIFEST.is_file():
        pytest.skip(f"no {MANIFEST}; run `dgt-scraper scrape` first")
    manifest: ManifestJson = json.loads(MANIFEST.read_text(encoding="utf-8"))
    numbers = [entry["number"] for entry in manifest["exams"]]
    if not numbers:
        pytest.skip("manifest lists no exams")
    return random.choice(numbers)


def _stored(number: int) -> ExamJson:
    path = DIST / f"exam-{number}" / "index.json"
    if not path.is_file():
        pytest.skip(f"{path} is not in dist/")
    loaded: ExamJson = json.loads(path.read_text(encoding="utf-8"))
    return loaded


async def _fetch_and_parse(number: int, cache_dir: Path) -> Exam:
    # A throwaway cache directory, so the page really comes off the network.
    async with Fetcher.create(cache_dir=cache_dir, rate=2.0, concurrency=1) as fetcher:
        page = await fetcher.exam_page(number)
    if page is None:
        pytest.fail(f"exam {number} is in dist/ but upstream now returns 404")
    content, url = page
    return parse_exam(content, number, url)


@pytest.mark.network
def test_upstream_matches_committed_data(tmp_path: Path) -> None:
    number = _pick_exam_number()
    stored = _stored(number)

    try:
        exam = asyncio.run(_fetch_and_parse(number, tmp_path / "cache"))
    except (httpx.TimeoutException, httpx.TransportError) as error:
        pytest.skip(f"revista.dgt.es unreachable: {error}")

    context = f"exam {number} (set DGT_EXAM_NUMBER={number} to re-run this one)"

    assert exam.title == stored["title"], context
    assert len(exam.questions) == len(stored["questions"]), context

    for parsed, expected in zip(exam.questions, stored["questions"], strict=True):
        where = f"{context} question {expected['number']}"
        assert parsed.number == expected["number"], where
        assert parsed.title == expected["title"], where
        assert parsed.image_source == expected["image_source"], where
        # image_alt is only stored when the image actually downloaded.
        if expected["image"] is not None:
            assert parsed.image_alt == expected["image_alt"], where

        assert len(parsed.answers) == len(expected["answers"]), where
        for answer, expected_answer in zip(
            parsed.answers, expected["answers"], strict=True
        ):
            assert answer.text == expected_answer["text"], where
            assert answer.correct == expected_answer["correct"], where
