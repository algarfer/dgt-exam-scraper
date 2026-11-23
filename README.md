# dgt-exam-scraper

Scrapes the monthly traffic-rules test that the Spanish DGT publishes in its magazine at
[revista.dgt.es](https://revista.dgt.es/) and turns it into static JSON plus local images.

> [!NOTE]
> This project has been partially vibecoded.
> All the code has been reviewed by myself.

## Output

Everything lands in `dist/`:

```
dist/
  manifest.json
  exam-NNN/
    index.json
    image-N.jpg
    ...
    image-NN.jpg
```

`manifest.json` lists every exam, newest first:

```json
{
  "$schema": "https://raw.githubusercontent.com/algarfer/dgt-exam-scraper/master/schemas/manifest.schema.json",
  "generated_at": "2026-11-08T17:09:30Z",
  "source": "https://revista.dgt.es/",
  "exams": [
    { "number": 279, "title": "Octubre 2026", "path": "exam-279/index.json" },
    ...
  ]
}
```

`exam-NNN/index.json` holds the test itself:

```json
{
  "$schema": "https://raw.githubusercontent.com/algarfer/dgt-exam-scraper/master/schemas/exam.schema.json",
  "number": 279,
  "title": "Octubre 2026",
  "url": "https://revista.dgt.es/es/test/Test-num-279.shtml",
  "scraped_at": "2026-11-08T17:09:30Z",
  "questions": [
    {
      "number": 1,
      "title": "Cuando no se pueda posicionar el vehículo paralelo al borde de la calzada, ...",
      "image": "image-1.jpg",
      "image_alt": "Aparcamiento",
      "image_source": "https://revista.dgt.es/Galerias/test/N-279/Test-279-P01-250x226.jpg",
      "answers": [
        { "text": "Sí, cuando las características de la vía u otras circunstancias así lo aconsejen.", "correct": true },
        { "text": "Sólo si existe alguna señal que permita el estacionamiento en batería.", "correct": false },
        { "text": "No, en ningún caso.", "correct": false },
        ...
      ],
      ...
    }
  ]
}
```

## Usage

The project is a [uv](https://docs.astral.sh/uv/) project. To install the dependencies run:

```sh
uv sync
```

Then:

```sh
# Scrape everything (first run takes a few minutes)
uv run dgt-scraper --verbose scrape

# One exam, handy while iterating
uv run dgt-scraper exam 279

# Look for a newly published exam and add it
uv run dgt-scraper --verbose latest
```

Common options, shared by all three subcommands:

| Option | Default | Meaning |
| --- | --- | --- |
| `--out` | `dist` | Output directory |
| `--cache` | `cache` | Where raw HTML is kept, so the parser can be re-run offline |
| `--rate` | `4` | Maximum requests per second |
| `--concurrency` | `4` | Maximum requests in flight |
| `--force` | off | Re-download pages and images that are already present |

`scrape` additionally takes `--from` / `--to` (default `1`–`279`), and `latest` takes
`--probe-ahead` (default `3`).

## Development

```sh
uv run mypy                     # strict typing
uv run pytest                   # includes the live upstream canary
uv run pytest -m "not network"  # fully offline
```

`tests/test_upstream.py` picks a random exam from `dist/`, re-fetches that page and re-parses it,
asserting the result still matches the committed JSON. It is a change-detector for DGT's markup:
if their HTML changes, it fails instead of letting the next scheduled run quietly write worse
data. Set `DGT_EXAM_NUMBER` to re-run it against one specific exam.

## How the pages are parsed

Useful if upstream ever breaks:

- exam title: `//h3[contains(@class,"tit_general")]`
- questions: `//article[contains(concat(" ",normalize-space(@class)," ")," test ")]` — the last
  question is `<article class="test ultimo">`, so an exact `class="test"` match silently drops it
- question title: `.//h4[contains(@class,"tit_not")]`, with the leading `N. ` stripped
- answers: `./section[contains(@class,"content_test")]/ul/li`, with the `A. ` prefix stripped
- correct answer: `.//div[contains(@class,"content_respuesta")]//span[contains(@class,"opcion")]`,
  matched back against each answer's own `span.opcion` letter
- image: `.//figure//img`

## License

[MIT](LICENSE).
