# Healthcare Intel Digest

A Python application that creates weekly healthcare and life-science stock intelligence reports from
Massive market data, public earnings pages, and report-specific strategy narratives.
Reports are generated as final versions immediately and stored in Git.

## What it produces

Healthcare reports are written to `reports/final/YYYY-MM-DD/`; Life Science and Device reports are
written to `reports/final/life-science-device/YYYY-MM-DD/`:

- `Healthcare Intel-YYYY-MM-DD.html`: self-contained report HTML with embedded charts, so it
  can be downloaded, previewed, or shared on its own.
- `Life Science and Device Intel-YYYY-MM-DD.html`: the same report format for the pharma,
  biotech, and device universe.
- `report.md` and `assets/`: diffable Markdown and lossless WebP chart images.
- `snapshot.csv`: the published performance values and ranks.
- `changes.csv`: every comparison with the previous eligible final.
- `render-data.json.gz`: a compact copy of the report-specific narrative, earnings, and
  reference inputs used for faithful network-free rerenders.
- `manifest.json`: data dates, configuration hash, source outcomes, quality warnings, stage
  timings, output sizes, and cache-retention results.

The scheduled workflow also publishes the self-contained HTML report as a conveniently named
GitHub Actions artifact.

A rerun for an existing date replaces that folder. The previous version remains available
through Git history.

## Local setup

Python 3.12 is required.

The one-command launcher reuses a compatible `.venv` even if the system's `python3`
still points to Python 3.9. When it needs to create the environment, it automatically looks
for `python3.12`, `python3.13`, `python3.14`, and then `python3`. You can also provide an
explicit interpreter with `ETHANOL_PYTHON=/path/to/python3.12 ./bin/run-report`.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m playwright install chromium
cp .env.example .env
```

Set `MASSIVE_API_KEY` and `OPENAI_API_KEY` in `.env` or export them in the shell. The CLI loads
the project `.env` automatically and never overrides variables already exported by the shell.

Validate the project and create a report:

```sh
python -m ethanol_report validate
python -m ethanol_report run

# Update only one report when needed:
python -m ethanol_report run --report healthcare
python -m ethanol_report run --report life-science-device
```

Create or recreate a report for a specific date:

```sh
python -m ethanol_report run --date 2026-08-03
```

If earnings or the narrative already ran for the same report date today, a rerun reuses them.
Use `--force-secondary` when those sources should be checked again regardless:

```sh
python -m ethanol_report run --date 2026-08-03 --force-secondary
```

Rebuild an existing report from its saved snapshot and cache without network or browser work:

```sh
python -m ethanol_report render --date 2026-08-03 --report healthcare
python -m ethanol_report render --date 2026-08-03 --report life-science-device
```

The renderer reuses only the charts required by that saved report. If chart styling changed,
regenerate them from the bounded price cache explicitly:

```sh
python -m ethanol_report render --date 2026-08-03 --refresh-charts
```

Create a portable single-file copy on demand:

```sh
python -m ethanol_report export-standalone --date 2026-08-03 --report healthcare
python -m ethanol_report export-standalone --date 2026-08-03 --output /tmp/report.html
```

The default standalone destination is `reports/standalone/`, which is ignored by Git.

Build the public website locally from all saved final reports:

```sh
python -m ethanol_report build-site
```

The generated `docs/` directory opens to the newest report and includes a past-report archive,
an About page, and a Methodology page. It is tracked in Git so a local report run produces the
exact static site that will be published. Both `run` and `render` rebuild it automatically;
`build-site` remains useful after editing only the About or Methodology copy.

Each published report has PDF and self-contained HTML downloads. Download buttons appear on the
latest report, each Past reports row, each weekly report card in News & Earnings, and the report's
own archive page. The site builder uses the installed Playwright Chromium to create a print-ready
PDF, then reuses unchanged PDFs through `docs/.download-manifest.json` on later builds.

The homepage always uses the latest Healthcare report. The Past reports page groups the archive
under Healthcare Intel Report and Life Sciences Intel Report. The News & Earnings page provides
a newest-first weekly index of report headlines and earnings-call coverage, with direct links to
the corresponding report sections. It also collects headlines under these business topics:

- Payers: Payer Strategy, Payment Integrity, Risk, and Quality;
- Providers: Provider Strategy, Revenue Cycle Management, Imaging, EDI & Interoperability, and
  Clinical Decision Support;
- Across the Business: Life Sciences, Policy & Cross-Sector, and Other.

Topic assignment is deterministic and based on headline wording. A headline can appear under
multiple relevant topics; unmatched headlines appear under Other. The weekly and topic indexes are
regenerated automatically from all saved final reports whenever `run`, `render`, or `build-site`
executes; there is no separate topic-index refresh step.

The normal local publishing flow is:

```sh
./bin/run-report
git add docs reports/final reports/strategy state
git commit -m "Create healthcare report for YYYY-MM-DD"
git push
```

Review `git status` before committing and add any intentional configuration, company-list, or
site-copy edits separately. GitHub Pages publishes the committed `docs/` directory directly,
so the deployed output is the version produced locally.

### One-command local runner

On macOS or Linux, the launcher handles the virtual environment, pinned dependencies,
Playwright Chromium, and the existing `.env` automatically:

```sh
./bin/run-report
```

This updates both report profiles. Use the Python CLI's `--report` option when only one profile
needs to be refreshed. Both strategy narratives run through the OpenAI Responses API with separate
prompts, histories, archives, and downstream latest files.

To create or replace a report for a particular date:

```sh
./bin/run-report 2026-08-03
```

The first invocation performs local setup and therefore takes longer. Later invocations reuse
`.venv` and reinstall only when `requirements.lock` or `pyproject.toml` changes. Useful
maintenance commands are:

```sh
./bin/run-report --validate
./bin/run-report --setup-only
```

Tests and static checks:

```sh
pytest
ruff check src tests
mypy src
```

## Configuration

- `inputs/companies.md` defines categories and their stocks using the original
  `Ticker: Name; Description` format. A ticker may belong to more than one category.
- `inputs/healthcare-strategy-prompt.md` is the version-controlled Healthcare research brief.
- `inputs/life-sciences-strategy-prompt.md` is the version-controlled pharmaceutical, biotech,
  life-sciences, and medical-device research brief.
- `config/settings.yaml` defines horizons, thresholds, source behavior, report presentation,
  report-profile category membership, and narrative freshness rules.

The Healthcare profile includes services, providers, real estate, value-based care, outpatient
and home care, digital health, health IT/data, pharma distribution, and precision diagnostics.
The Life Science and Device profile includes Devices & Diagnostic, Big Pharma, Established Biotech,
and Emerging Biotech.

The report date and its automatic earnings selections are runtime values rather than mutable
configuration. This keeps scheduled reports reproducible.

### Edit categories and tracked stocks

Open the single human-editable company file:

```sh
open -a TextEdit inputs/companies.md
```

Categories and stocks live in the YAML front matter between the two `---` lines:

```yaml
Managed Care:
  UNH: UnitedHealth; Diversified healthcare and health-services company.
  HUM: Humana; Medicare-focused health insurer.
Biopharma:
  LLY: Lilly; Global biopharmaceutical company.
```

Add, remove, or rename categories directly in this block. Repeat the exact same stock line
under another category when a company belongs to more than one. Validate edits before the
next report:

```sh
bin/run-report --validate
```

## Performance comparisons

The latest earlier final at least five days old is the comparison baseline. For every 3-,
12-, and 24-month horizon, the snapshot records:

- each subcategory's rank across subcategories;
- each stock's rank across the complete watchlist;
- each stock's rank within every assigned subcategory;
- returns, market capitalization, coverage, and the actual price date.

The next report compares the stored published ranks directly. It does not recompute ranks
over only the companies common to both reports, so additions and removals cannot silently
hide a change. Rank and return deltas appear in the report, while `changes.csv` retains the
complete unfiltered comparison ledger.

The first Python report establishes the baseline because the former R workflow never saved a
final snapshot in Git.

## Durable data cache

Provider responses are checkpointed under `state/cache/` as soon as each request succeeds:

- company profiles are reused for 90 days;
- new tickers receive one full-history price request, while routine updates use Massive's
  grouped-daily endpoint to update all cached tickers when that reduces the request count;
- after a successful report, price history older than the longest configured horizon plus
  the 45-day safety buffer is removed.

Stopping a run does not discard completed market requests. The next run resumes from the
saved ticker or date range. On this computer, the cache also imports usable company and price
history from the former R workflow's local `data/` files once, avoiding unnecessary initial
downloads.

The cache contains no API credentials. GitHub Actions commits it with the rest of `state/`, so
scheduled cloud runs reuse the prior run's data and only fetch updates.

## Earnings dates

Google Finance is checked anonymously through Playwright; Yahoo is the date fallback. If a
last earnings date is known but the next one is not:

- the tentative event date is last earnings + 90 days;
- the next confirmation check is last earnings + 69 days;
- the report labels the date as tentative;
- scheduled runs check weekly from day 69 until a source confirms the date.

A confirmed date is rechecked weekly during its final 21 days. Missing secondary data does
not suppress otherwise valid market analysis and remains recorded in `manifest.json`.

## Strategy narrative

Both profiles generate their weekly strategy briefs with the OpenAI Responses API using GPT-5.6
Sol, high reasoning, and built-in web search by default. Each request explicitly supplies the report
date, prior-seven-day window, profile-specific master prompt, and that profile's four newest prior
reports. Reports are persisted under:

```text
reports/strategy/healthcare/YYYY-MM-DD.md
reports/strategy/healthcare/YYYY-MM-DD.json
reports/strategy/healthcare/latest.md
reports/strategy/healthcare/latest.json
reports/strategy/life-science-device/YYYY-MM-DD.md
reports/strategy/life-science-device/YYYY-MM-DD.json
reports/strategy/life-science-device/latest.md
reports/strategy/life-science-device/latest.json
state/strategy-runs-healthcare.jsonl
state/strategy-runs-life-science-device.jsonl
```

The dated files are permanent history. `latest.md` and `latest.json` are replaced only after a
successful, validated response, so downstream Python code can read either profile's stable location.
The narratives are also written to `state/narrative.json` and
`state/narrative-life-science-device.json` for the existing market-report renderer. If an API run
fails, the last good narrative remains in place and the report is marked degraded.

Generate or inspect an individual strategy brief with:

```sh
python -m ethanol_report generate-strategy
python -m ethanol_report generate-strategy --dry-run
python -m ethanol_report generate-strategy --date 2026-08-24
python -m ethanol_report generate-strategy --date 2026-08-24 --force
python -m ethanol_report generate-strategy --report life-science-device
python -m ethanol_report generate-strategy --report life-science-device --dry-run
python -m ethanol_report generate-strategy --report life-science-device --date 2026-08-24 --force
```

The CLI loads `.env` without overriding variables already supplied by the shell. Supported
configuration is:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-sol
OPENAI_REASONING_EFFORT=high
REPORT_HISTORY_COUNT=4
OPENAI_MAX_OUTPUT_TOKENS=16000
OPENAI_TIMEOUT_SECONDS=900
```

Set `OPENAI_MODEL=gpt-5.6-terra` for a lower-cost development run without changing code. Usage,
web-search-call count, request identifiers, and estimated cost are recorded in the JSON report and
JSONL run log. Cost estimates use the centralized model-price table in
`src/ethanol_report/strategy.py`; update it when OpenAI pricing changes. The API key is read only
from the environment and must never be committed.

Refresh either profile's API-backed narrative snapshot with:

```sh
python -m ethanol_report refresh-narrative --report healthcare
python -m ethanol_report refresh-narrative --report life-science-device
```

## GitHub automation

The **Run full healthcare update** workflow runs every Monday at 8:00 AM America/Denver and
updates both report profiles. Manual dispatch accepts an optional report date and a report scope
of Healthcare, Life Science and Device, or Both. Add both `MASSIVE_API_KEY` and `OPENAI_API_KEY`
under **Settings → Secrets and variables → Actions**, and allow GitHub Actions read/write
repository permissions. A manual run forces fresh earnings and strategy-narrative checks, even if
those sources were already checked that day.

The workflow runs at 8:00 AM Monday in `America/Denver`; GitHub's timezone-aware schedule handles
Mountain Time daylight-saving changes. A successful run commits both dated strategy archives,
stable latest files, final market reports, state, and the rebuilt site.

The workflow validates and tests the project, installs anonymous Chromium, creates the final,
uploads the standalone HTML artifact for 90 days, commits the final report plus compact `state/`
using `github-actions[bot]`, and deploys the refreshed public site. If core market analysis
cannot be built, it commits nothing. Earnings or narrative failures yield a degraded manifest
while preserving the valid market report.

The workflow verifies that the branch has not changed while it runs and pushes through
`github-actions[bot]`. It deploys Pages only when it committed a changed report or state snapshot.

### Strategy troubleshooting

- `OPENAI_API_KEY is not configured`: confirm `.env` is in the repository root for local runs, or
  confirm the Actions secret name is exactly `OPENAI_API_KEY`.
- Authentication or permission errors are not retried indefinitely; correct the key or project
  access and rerun. Transient API and network failures receive the SDK's bounded retries.
- An existing dated strategy file causes a no-op. Use `--force` only when intentionally replacing
  that date's report.
- A failed or invalid response is recorded in that profile's `state/strategy-runs-*.jsonl` and
  never replaces its prior `latest.md`.

### GitHub Pages

For the primary local publishing path, open the repository's **Settings → Pages**, choose
**Deploy from a branch**, select `master`, select `/docs`, and save. A local push then publishes
the exact generated files committed under `docs/`.

The **Rebuild GitHub Pages site** workflow is a manual cloud fallback that regenerates and
commits `docs/`, then explicitly requests a Pages build. The full scheduled-report workflow
does the same after producing a new report because GitHub does not automatically start a
branch-based Pages build for commits pushed with the workflow's `GITHUB_TOKEN`.

Public page copy lives in `site_content/about.md` and `site_content/methodology.md`. The site
generator automatically publishes legacy Healthcare folders and report-profile folders under
`reports/final/`, lists both types in the Past reports archive, sorts newest-first, and uses the
newest report as the homepage.
