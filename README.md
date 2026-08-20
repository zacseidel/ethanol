# Corn and Ethanol Intel

A Python application that creates a weekly corn and ethanol intelligence report from Massive market data, public earnings pages, and an OpenAI strategy brief. Reports are generated as finals immediately and stored in Git.

This is a single-profile port of the Healthcare Intel Digest workflow. There is one watchlist, one strategy prompt, and one published report each week.

## What it produces

Reports are written to `reports/final/YYYY-MM-DD/`:

- `Corn and Ethanol Intel-YYYY-MM-DD.html`: self-contained report HTML with embedded charts
- `report.md` and `assets/`: diffable Markdown and WebP charts
- `snapshot.csv`, `changes.csv`, `render-data.json.gz`, `manifest.json`

The strategy archive lives at `reports/strategy/ethanol/`.

The scheduled workflow publishes the self-contained HTML report as a GitHub Actions artifact.

## Local setup

Python 3.12 is required.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m playwright install chromium
cp .env.example .env
```

Set `MASSIVE_API_KEY` and `OPENAI_API_KEY` in `.env`. Never copy keys from another project.

```sh
python -m ethanol_report validate
python -m ethanol_report run
python -m ethanol_report run --date 2026-08-03
```

Same-date strategy generation is reused unless you pass `--force-secondary` (full run) or `--force` (strategy only).

```sh
python -m ethanol_report render --date 2026-08-03
python -m ethanol_report generate-strategy --dry-run
./bin/run-report
```

`./bin/run-report` creates or replaces today's report. `./bin/run-report 2026-08-03` uses that date.

Build the public site:

```sh
python -m ethanol_report build-site
```

The generated `docs/` directory is the GitHub Pages source.

## Configuration

- `inputs/companies.md` — YAML front matter, `Ticker: Name; Description`
- `inputs/ethanol-strategy-prompt.md` — version-controlled research brief
- `config/settings.yaml` — horizons, cache, timezone (`America/Chicago`), single `ethanol` profile
- `docs/universe.md` — human research notes for the watchlist

Edit categories in the YAML block, then `./bin/run-report --validate`.

## GitHub

Add repository secrets `MASSIVE_API_KEY` and `OPENAI_API_KEY`. The weekly workflow runs Thursday 19:00 America/New_York. Pages should deploy from the default branch `/docs`.

Tests:

```sh
pytest
ruff check src tests
mypy src
```
