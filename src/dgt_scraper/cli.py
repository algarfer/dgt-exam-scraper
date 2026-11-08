"""Command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from dgt_scraper.fetch import Fetcher
from dgt_scraper.parser import ParseError, parse_exam
from dgt_scraper.writer import manifest_numbers, write_exam, write_manifest

__all__ = ["main"]

_log: Final = logging.getLogger("dgt_scraper")

DEFAULT_OUT: Final = Path("dist")
DEFAULT_CACHE: Final = Path("cache")
DEFAULT_RATE: Final = 4.0
DEFAULT_CONCURRENCY: Final = 4
DEFAULT_FIRST: Final = 1
DEFAULT_LAST: Final = 279
DEFAULT_PROBE_AHEAD: Final = 3


@dataclass(slots=True)
class Outcome:
    """What a run did, so the caller can report and set an exit code."""

    scraped: list[int]
    missing: list[int]
    failed: list[int]

    @property
    def ok(self) -> bool:
        return not self.failed


async def _scrape_numbers(
    numbers: list[int],
    *,
    out_dir: Path,
    cache_dir: Path,
    rate: float,
    concurrency: int,
    force: bool,
) -> Outcome:
    outcome = Outcome(scraped=[], missing=[], failed=[])
    async with Fetcher.create(
        cache_dir=cache_dir, rate=rate, concurrency=concurrency, force=force
    ) as fetcher:

        async def handle(number: int) -> None:
            try:
                page = await fetcher.exam_page(number)
            except httpx.HTTPError as error:
                _log.error("exam %s: fetch failed: %s", number, error)
                outcome.failed.append(number)
                return
            if page is None:
                _log.debug("exam %s does not exist", number)
                outcome.missing.append(number)
                return

            content, url = page
            try:
                exam = parse_exam(content, number, url)
            except ParseError as error:
                _log.error("%s", error)
                outcome.failed.append(number)
                return

            try:
                await write_exam(exam, out_dir, fetcher)
            except httpx.HTTPError as error:
                _log.error("exam %s: image download failed: %s", number, error)
                outcome.failed.append(number)
                return

            _log.info(
                "exam %s: %s (%d questions)", number, exam.title, len(exam.questions)
            )
            outcome.scraped.append(number)

        await asyncio.gather(*(handle(number) for number in numbers))

    if outcome.scraped:
        write_manifest(out_dir)
    outcome.scraped.sort()
    outcome.missing.sort()
    outcome.failed.sort()
    return outcome


async def _latest_numbers(
    *, out_dir: Path, cache_dir: Path, rate: float, probe_ahead: int
) -> list[int]:
    """Numbers worth trying when looking for a newly published exam."""
    known = manifest_numbers(out_dir) if out_dir.is_dir() else []
    highest = max(known, default=0)

    async with Fetcher.create(cache_dir=cache_dir, rate=rate, concurrency=1) as fetcher:
        try:
            advertised = await fetcher.index_numbers()
        except httpx.HTTPError as error:
            _log.warning("could not read the index page: %s", error)
            advertised = []

    start = max([highest, *advertised], default=0)
    candidates = {number for number in advertised if number not in known}
    candidates.update(range(start + 1, start + 1 + probe_ahead))
    return sorted(number for number in candidates if number > 0 and number not in known)


def _report(outcome: Outcome) -> None:
    print(
        f"scraped={len(outcome.scraped)} "
        f"missing={len(outcome.missing)} "
        f"failed={len(outcome.failed)}"
    )
    if outcome.scraped:
        print(f"new-or-updated: {' '.join(str(n) for n in outcome.scraped)}")
    if outcome.failed:
        print(f"failed: {' '.join(str(n) for n in outcome.failed)}", file=sys.stderr)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output directory (default: dist)"
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE,
        help="directory for raw HTML (default: cache)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE,
        help="maximum requests per second (default: 4)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="maximum requests in flight (default: 4)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download pages and images even when already present",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dgt-scraper", description="Scrape the DGT tests published at revista.dgt.es"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log every exam processed"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape = subparsers.add_parser("scrape", help="scrape a range of exams")
    scrape.add_argument(
        "--from",
        dest="first",
        type=int,
        default=DEFAULT_FIRST,
        help=f"first exam number (default: {DEFAULT_FIRST})",
    )
    scrape.add_argument(
        "--to",
        dest="last",
        type=int,
        default=DEFAULT_LAST,
        help=f"last exam number (default: {DEFAULT_LAST})",
    )
    _add_common(scrape)

    exam = subparsers.add_parser("exam", help="scrape a single exam")
    exam.add_argument("number", type=int)
    _add_common(exam)

    latest = subparsers.add_parser("latest", help="look for newly published exams")
    latest.add_argument(
        "--probe-ahead",
        type=int,
        default=DEFAULT_PROBE_AHEAD,
        help=(
            "how many numbers past the newest known exam to probe "
            f"(default: {DEFAULT_PROBE_AHEAD})"
        ),
    )
    _add_common(latest)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.command == "scrape":
        if args.first > args.last:
            print("--from must not be greater than --to", file=sys.stderr)
            return 2
        numbers = list(range(args.first, args.last + 1))
    elif args.command == "exam":
        numbers = [args.number]
    else:
        numbers = asyncio.run(
            _latest_numbers(
                out_dir=args.out,
                cache_dir=args.cache,
                rate=args.rate,
                probe_ahead=args.probe_ahead,
            )
        )
        if not numbers:
            print("scraped=0 missing=0 failed=0")
            print("no new exams")
            return 0
        _log.info("probing %s", " ".join(str(number) for number in numbers))

    outcome = asyncio.run(
        _scrape_numbers(
            numbers,
            out_dir=args.out,
            cache_dir=args.cache,
            rate=args.rate,
            concurrency=args.concurrency,
            force=args.force,
        )
    )
    _report(outcome)
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
