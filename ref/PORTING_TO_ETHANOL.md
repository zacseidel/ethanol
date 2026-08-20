# Porting the Intelligence Workflow to Ethanol

## Purpose

This document is the controlling handoff brief for creating a separate ethanol-focused
intelligence application from the existing Healthcare Intel Digest repository.

The ethanol application should preserve the existing workflow, logic, schemas, reliability
characteristics, generated artifacts, website behavior, and operational model. It should replace
the healthcare and life-sciences subject matter, company universe, branding, prompt, topic
taxonomy, and deployment identity.

Treat the existing repository as the executable specification. Do not rebuild the application
from a prose description when working, tested implementation is available.

The desired result is a separate, independently configured repository and deployment. It must
not share credentials, generated reports, historical state, caches, or GitHub Pages output with
the healthcare application.

## Guiding principle

Create a small, boring, reliable ethanol research pipeline with the same architecture as the
current application. Make the smallest domain-specific changes necessary. Do not introduce a
general agent framework or redesign working infrastructure without a demonstrated ethanol need.

## Current end-to-end architecture

```text
Company universe + configuration
        ↓
Market data and earnings collection
        ↓
Returns, rankings, changes, and prior-report baseline
        ↓
OpenAI strategy research with recent report history
        ↓
Cached-narrative fallback if the API call fails
        ↓
Markdown, charts, HTML, snapshots, and manifest
        ↓
Static website, archive, topic index, and HTML/PDF downloads
        ↓
GitHub Actions commit and GitHub Pages publication
```

The main orchestration is in `src/healthcare_report/pipeline.py`. The OpenAI Responses API
workflow is in `src/healthcare_report/strategy.py`. Configuration and report profiles are loaded
by `src/healthcare_report/config.py`. Report rendering is in `src/healthcare_report/render.py`,
and public-site generation is in `src/healthcare_report/site.py`.

## Important clarification about fallback behavior

The current application does not scrape an old ChatGPT Scheduled Task when the OpenAI API call
fails.

The implemented fallback is:

1. Attempt to generate the strategy narrative through the OpenAI Responses API.
2. If generation fails, record the error and mark the strategy source with a warning.
3. Reuse the last cached successful narrative when one exists.
4. If no cached narrative exists, continue without one and surface the source/quality warning.
5. Do not overwrite the latest successful standalone strategy report with a failed result.

This behavior is implemented in `src/healthcare_report/narrative.py`. Preserve it in the ethanol
port unless the owner explicitly requests a different fallback.

## What must remain functionally identical

Preserve the following behaviors and contracts:

- One-command local report generation.
- Weekly scheduled execution and manual execution.
- Explicit report date and timezone handling.
- Public-company market-data collection and durable caching.
- Earnings discovery and stored earnings state.
- Configurable benchmark and return/chart horizons.
- Published snapshots, ranks, changes, and previous-report comparisons.
- Baseline selection from the latest eligible earlier final report.
- OpenAI Responses API, reasoning configuration, and built-in web search.
- Explicit inclusion of recent prior strategy reports in the assembled prompt.
- Version-controlled master strategy prompt.
- Idempotent strategy generation for an existing report date.
- Usage, web-search-call, model, reasoning, and estimated-cost logging.
- Safe writes and atomic promotion of completed report directories.
- Cached-narrative fallback after an OpenAI failure.
- Markdown report, rendered HTML, charts, CSV snapshots, compressed render data, and manifest.
- Network-free rerendering from saved artifacts.
- Static homepage, report archive, topic index, About page, and Methodology page.
- PDF and self-contained HTML downloads.
- Automatic rebuilding of the topic index whenever a report or site is built.
- GitHub Actions validation, generation, artifact upload, commit, and Pages publication.
- Ruff, mypy, pytest, and configuration validation.
- Credential redaction and the rule that secrets never enter source control or logs.

## What must be replaced for ethanol

Replace or review all of the following:

- Project, package, CLI, workflow, and artifact branding.
- Report name, slug, description, and filenames.
- Company categories, tickers, names, and descriptions.
- Benchmark ticker.
- Ethanol strategy master prompt.
- Strategy profile metadata and expected report heading.
- CLI report-profile choices.
- Narrative heading-removal rules.
- Report titles and default-name fallbacks in the renderer.
- Site brand, page titles, footer, archive grouping, and homepage-selection logic.
- Topic-index groups, labels, keyword rules, and special-case classification logic.
- About and Methodology copy.
- Report color palette, typography, accents, tables, charts, and print treatment.
- Public-site color palette, typography, navigation, cards, buttons, and page treatment.
- GitHub Actions display names, concurrency group, artifact name, summary text, and commit message.
- Repository-specific API secrets and GitHub Pages configuration.
- Tests containing healthcare or life-sciences names, profile choices, filenames, headings, or
  topic expectations.

## Domain decisions required before implementation

Record these decisions in this file or a companion `ETHANOL_REQUIREMENTS.md` before making large
changes:

### Identity

- Final report name: **TBD**
- Short navigation/site brand: **TBD**
- Repository name: **TBD**
- Python distribution name: **TBD**
- Python package/module name: **TBD**
- CLI command name: **TBD**
- Report slug: `ethanol` unless another slug is intentionally selected

### Schedule

- Business timezone: **TBD**
- Weekly publication day and local time: **TBD**
- Manual workflow behavior: preserve the current optional date and force-refresh controls

### Market universe

- Category list: **TBD**
- Public-company tickers and descriptions: **TBD**
- Equity benchmark: **TBD**
- Return horizons: **TBD or preserve current values**
- Chart horizons: **TBD or preserve current values**

### Strategy research

- Master ethanol prompt: **TBD**
- Expected report title: **TBD**
- Default OpenAI model: preserve `gpt-5.6-sol` unless intentionally changed
- Default reasoning effort: preserve `high` unless intentionally changed
- Prior strategy reports supplied: preserve four unless intentionally changed
- Reporting window: preserve the prior seven days unless intentionally changed

### Website

- Primary and secondary colors: **TBD**
- Accent colors: **TBD**
- Typography direction: **TBD**
- Topic groups and keyword patterns: **TBD**
- About copy: **TBD**
- Methodology copy: **TBD**

## Ethanol data-scope decision

The existing quantitative pipeline is designed around public securities available through
Massive and earnings information discoverable on public financial pages. A different list of
public ethanol-related companies can use that workflow directly.

Decide explicitly whether the ethanol report also requires non-equity inputs, such as:

- Physical ethanol prices.
- Corn prices.
- Natural-gas prices.
- Crude-oil or gasoline prices.
- Renewable Identification Number prices.
- Crush or production-margin estimates.
- EIA production, inventory, blending, or export data.
- USDA crop, acreage, yield, or stocks data.
- Plant capacity, utilization, outage, or maintenance data.
- Policy-credit values or low-carbon fuel-standard data.

If these are required, preserve the overall workflow and schemas but add narrowly scoped provider
modules with their own caching, source status, validation, and tests. Do not represent commodities
or industry statistics as ordinary equity tickers merely to avoid adding an appropriate provider.

## Credential isolation

Never copy `.env` from the healthcare repository.

For a separate directory and separate GitHub repository, continue using the standard runtime
environment-variable interface:

```text
OPENAI_API_KEY
MASSIVE_API_KEY
```

The ethanol `.env` and ethanol repository secrets can use completely different values while
retaining these variable names. Separate repositories isolate their secrets.

If both applications are ever executed in a shared repository or shared GitHub Actions job, give
the stored secrets ethanol-specific names and map them to the standard runtime variables:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.ETHANOL_OPENAI_API_KEY }}
  MASSIVE_API_KEY: ${{ secrets.ETHANOL_MASSIVE_API_KEY }}
```

Never print, inspect, migrate, transform, or commit the actual secret values.

## Clean-copy rules

Begin from a committed or tagged version of the healthcare repository for which all tests pass.
Copy the implementation to the new ethanol directory, but do not copy generated or private state.

Do not carry these into the ethanol project:

```text
.env
docs/
reports/final/
reports/strategy/
reports/standalone/
state/cache/
state/earnings.json
state/narrative*.json
state/strategy-runs-*.jsonl
report-result.json
```

Generated healthcare and life-sciences data would contaminate:

- Baseline selection.
- Prior-report comparisons.
- LLM report history.
- Latest-report selection.
- Topic-index content.
- Download manifests.
- API usage logs.

Retain the source tree, tests, dependency lockfile, configuration structure, launcher, workflows,
and generic fixtures. Replace domain-specific test data deliberately.

## File-by-file migration map

### `config/settings.yaml`

- Replace the default report identity.
- Replace `report_profiles` with the ethanol profile.
- Set the ethanol category membership.
- Confirm benchmark, timezone, horizons, thresholds, cache behavior, and narrative freshness.
- Prefer a single `ethanol` profile unless multiple ethanol report universes are explicitly needed.

### `inputs/companies.md`

- Replace all healthcare categories and companies.
- Preserve the YAML-front-matter structure.
- Preserve the `Ticker: Name; Description` format.
- Repeat an identical company entry across categories when multi-category membership is desired.
- Validate that every profile category exists and every ticker is acceptable to the market-data
  provider.

### `inputs/*-strategy-prompt.md`

- Create a version-controlled ethanol master prompt.
- Define the ethanol research scope, source priority, delta-first inclusion test, expected analysis,
  report structure, date handling, and citation requirements.
- Ensure the expected Markdown heading agrees with the strategy profile and validator.
- Remove the healthcare and life-sciences prompts from the new project once no code or tests depend
  on them.

### `src/healthcare_report/config.py`

- Remove assumptions that make `healthcare` the default/root profile.
- Make the ethanol profile the default.
- Preserve configuration validation, universe parsing, duplicate-ticker consistency checks, and
  path behavior.
- Decide whether to rename the Python package in a separate, mechanical step.

### `src/healthcare_report/strategy.py`

- Replace `STRATEGY_PROFILES` with an ethanol profile.
- Set the prompt filename, expected report title, analyst domain, and task subject.
- Generalize healthcare-specific validation error messages.
- Preserve request assembly, history delimiters, prompt hashing, web search, response extraction,
  citation preservation, usage extraction, pricing configuration, idempotency, and atomic writes.

### `src/healthcare_report/narrative.py`

- Make narrative state paths work for the ethanol profile.
- Replace the title-removal expression so it recognizes the ethanol strategy heading.
- Preserve cached fallback and source-warning behavior.

### `src/healthcare_report/analysis.py`

- Preserve ranking, return, comparison, and baseline logic unless an ethanol requirement makes a
  specific change necessary.
- Add tests before changing any published calculation or schema.

### `src/healthcare_report/providers.py`

- Preserve Massive caching, rate limiting, retry behavior, source status, and redaction.
- Change the user-agent/project label.
- Add providers only if non-equity ethanol data is explicitly required.

### `src/healthcare_report/earnings.py`

- Preserve the refresh-state and earnings-window behavior for public companies.
- Confirm the selected ethanol companies are covered adequately by the existing sources.
- Add a provider fallback only when tests or a real dry run demonstrate a coverage problem.

### `src/healthcare_report/render.py`

- Replace report-name and filename fallbacks.
- Replace healthcare-specific headings and explanatory copy.
- Implement the ethanol report visual scheme in the report CSS near the top of the file.
- Update chart colors and semantic accents consistently.
- Preserve responsive layout, accessible contrast, tables, anchors, embedded assets, standalone
  export, and print behavior.

### `src/healthcare_report/site.py`

- Replace site branding, HTML title suffix, footer, archive groups, and homepage report selection.
- Replace `TOPIC_GROUPS` with a deterministic ethanol taxonomy.
- Replace special-case healthcare/life-sciences classification.
- Implement the ethanol public-site visual scheme in `SITE_CSS`.
- Preserve archive generation, topic-index rebuilding, report decoration, download links, cached PDF
  generation, and atomic site replacement.

### `src/healthcare_report/cli.py`

- Replace hard-coded report choices with `ethanol`, or derive valid choices from configuration if
  that can be done simply and reliably.
- Replace CLI help and program naming.
- Preserve `run`, `render`, `export-standalone`, `build-site`, `validate`, `refresh-narrative`, and
  `generate-strategy` behavior.

### `bin/run-report`

- Replace user-facing healthcare names and examples.
- Preserve environment setup, locked dependency installation, `.env` loading, API-key validation,
  Playwright installation, and command forwarding.
- Do not weaken the credential checks.

### `site_content/about.md` and `site_content/methodology.md`

- Replace all healthcare subject matter.
- Accurately describe ethanol sources, calculations, LLM research, history, caveats, and publication
  process.
- Do not claim access to commodity or government datasets unless the application actually retrieves
  them.

### `.github/workflows/*.yml`

- Replace workflow names, concurrency groups, summary headings, artifact names, and commit messages.
- Configure the intended ethanol schedule and timezone.
- Use repository-specific secrets.
- Preserve validation before paid generation.
- Preserve branch-change protection before committing.
- Preserve commit scope so generated reports, site, strategy archives, and state are persisted.
- Preserve manual `workflow_dispatch` with optional report date.

### `pyproject.toml`

- Replace distribution metadata and console-script name.
- Rename the package only if the rename is performed consistently across imports, tests, coverage,
  mypy configuration, and the launcher.
- Keep Python and dependency constraints pinned until the port passes.

### `README.md`

- Rewrite for ethanol setup, operation, output paths, history, fallbacks, downloads, scheduling,
  costs, and troubleshooting.
- Document any ethanol-specific data providers and API keys.

### `tests/`

- Preserve the breadth of the existing test suite.
- Replace domain names, report headings, filenames, scope choices, archive groups, and topic-index
  expectations.
- Add tests for every new provider or schema.
- Keep external API calls mocked in unit tests.

## Recommended migration sequence

### Stage 1: Establish a clean baseline

1. Start from a committed/tagged healthcare revision.
2. Copy it into the new directory without private or generated state.
3. Create a new Git repository if appropriate.
4. Install locked dependencies and Playwright Chromium.
5. Run validation and the complete test suite before changing code.
6. Record the baseline commands and outcomes.

### Stage 2: Define the ethanol domain

1. Finalize identity, schedule, company categories, tickers, benchmark, prompt, topic taxonomy,
   visual direction, and data-source requirements.
2. Decide whether public-equity data alone is sufficient.
3. If additional providers are needed, specify their exact data contracts before implementation.

### Stage 3: Create the ethanol profile

1. Replace configuration and company inputs.
2. Add the ethanol strategy prompt and strategy profile.
3. Update CLI profile choices and state/output paths.
4. Update filenames and report headings.
5. Run configuration, prompt-assembly, and strategy tests.

### Stage 4: Rebrand without changing workflow logic

1. Update package/project metadata and launcher text.
2. Update report rendering and chart palette.
3. Update website branding and public-page palette.
4. Replace topic groups and keyword patterns.
5. Replace About and Methodology content.
6. Update domain-specific site and rendering tests.

### Stage 5: Update automation

1. Create the ethanol GitHub Actions workflow.
2. Map repository-specific secrets.
3. Update artifact and commit naming.
4. Confirm the local-time schedule and daylight-saving behavior.
5. Confirm GitHub Pages publishes the ethanol `docs/` directory.

### Stage 6: Verify without paid API calls

Run:

```sh
python -m <ethanol_package> validate
ruff check src tests
mypy src
pytest
python -m <ethanol_package> generate-strategy --report ethanol --dry-run
```

Then verify:

- The assembled prompt contains the correct ethanol prompt and dates.
- It contains no healthcare or life-sciences controlling instructions.
- Prior reports are clearly delimited as untrusted reference material.
- No live OpenAI request was made.
- The site can be built from test fixtures.
- Report, archive, topic, PDF, and HTML links resolve.
- Generated PDFs begin with a valid PDF signature.
- No secrets appear in output, logs, manifests, or generated pages.

### Stage 7: Perform one controlled live run

Only after the preceding checks pass:

1. Add the ethanol API keys to the new local `.env`.
2. Run one dated ethanol report.
3. Review source warnings, report content, strategy citations, market coverage, and estimated cost.
4. Review the HTML and PDF visually on desktop and mobile widths.
5. Run the same date again and verify it does not create duplicate paid strategy reports.
6. Simulate or mock an OpenAI failure and verify the cached fallback behavior.
7. Review `git status` carefully before the first commit.

## Schemas and artifacts to preserve

Each final report should continue to contain the equivalent of:

```text
reports/final/<report-date>/
    <Ethanol Report Name>-<report-date>.html
    report.md
    snapshot.csv
    changes.csv
    render-data.json.gz
    manifest.json
    assets/
```

The strategy archive should preserve dated Markdown and JSON plus stable latest files:

```text
reports/strategy/ethanol/
    YYYY-MM-DD.md
    YYYY-MM-DD.json
    latest.md
    latest.json
```

The public site should preserve:

```text
docs/
    index.html
    reports/index.html
    news/index.html
    about/index.html
    methodology/index.html
    reports/<report-date>/index.html
    reports/<report-date>/<download-name>.html
    reports/<report-date>/<download-name>.pdf
    .download-manifest.json
```

If output paths are renamed, update all producers, consumers, workflows, tests, documentation, and
Git staging rules together.

## Reliability invariants

The port is not complete if any of these are weakened:

- A failed render must not replace the last complete dated report directory.
- A failed site build must not replace the last complete site.
- A failed OpenAI request must not replace the latest successful strategy archive.
- A same-date rerun must not silently create duplicate paid strategy generations.
- Cached data must be reusable after transient provider failures.
- Every source failure must be visible in status records or report quality warnings.
- The API key must never be logged or committed.
- Previous reports must be treated as reference material, not instructions.
- The current reporting date and window must be supplied explicitly to the model.
- Topic indexes must be regenerated from saved final reports rather than maintained manually.
- Generated download links must resolve to real HTML and PDF artifacts.
- Tests must not require live API calls.

## Suggested ethanol topic-index design

Do not adopt this example without owner approval, but use it as a starting point for the required
taxonomy decision:

```text
Markets & Margins
    Ethanol Prices
    Corn and Feedstocks
    Energy and Natural Gas
    RINs and Policy Credits
    Crush Margins

Operations & Supply
    Production and Capacity
    Inventories and Blending
    Plant Outages and Maintenance
    Logistics and Rail
    Exports

Companies & Capital
    Company Strategy
    Earnings
    M&A and Partnerships
    Capital Projects
    Balance Sheets and Financing

Policy & Technology
    Renewable Fuel Standard
    Tax Credits and Regulation
    Carbon Capture
    Sustainable Aviation Fuel
    Low-Carbon Fuel Standards
    New Technologies

Other
```

Topic assignment in the existing site is deterministic keyword matching against report headlines.
Define explicit, testable patterns for every approved ethanol topic. Do not replace this with an
unbounded LLM classification call unless the owner requests that architectural change.

## Acceptance criteria

The ethanol port is complete when:

- [ ] It exists in a separate directory and repository.
- [ ] It uses separate local and GitHub credentials.
- [ ] No healthcare report, cache, strategy history, or state was copied into it.
- [ ] One local command generates the complete ethanol report.
- [ ] The configured public-company universe is validated.
- [ ] The selected benchmark and all quantitative horizons are documented.
- [ ] The OpenAI Responses API and built-in web search are enabled.
- [ ] The ethanol prompt is version controlled.
- [ ] The prior four ethanol strategy reports are supplied for delta analysis when available.
- [ ] The strategy output is validated for heading, length, date, content, and source links.
- [ ] Same-date strategy generation is idempotent unless explicitly forced.
- [ ] OpenAI usage and estimated cost are logged without exposing credentials.
- [ ] An OpenAI failure preserves and reuses the last cached narrative when available.
- [ ] Final reports are stored by date with snapshot, change, render-data, and manifest artifacts.
- [ ] The latest report appears on the homepage.
- [ ] The archive contains all saved ethanol reports.
- [ ] The ethanol topic index rebuilds automatically.
- [ ] PDF and self-contained HTML downloads work from every intended page.
- [ ] The report and public site use the approved ethanol visual scheme.
- [ ] The weekly GitHub Actions workflow uses the intended local business time.
- [ ] Manual workflow execution supports an explicit report date.
- [ ] Successful scheduled runs commit reports, strategy history, state, and `docs/`.
- [ ] GitHub Pages publishes the committed ethanol site.
- [ ] Configuration validation passes.
- [ ] Ruff passes.
- [ ] Mypy passes.
- [ ] All unit tests pass without live API calls.
- [ ] One controlled live report has been reviewed successfully.
- [ ] README instructions are sufficient for a fresh machine.

## Controlling prompt for the receiving LLM

Use the following when handing the clean repository copy to another LLM:

```text
You are porting an existing, tested healthcare intelligence application into a
separate ethanol intelligence application.

Read PORTING_TO_ETHANOL.md completely before taking any action. Treat the existing
repository as the executable specification. Preserve its workflow, persistence
schemas, history handling, caching, comparison logic, OpenAI Responses API
integration, failure behavior, report artifacts, static site, topic-index rebuilding,
HTML/PDF downloads, scheduling, and tests.

Do not rebuild the application from scratch.

First inspect and document the current architecture and run the existing validation,
Ruff, mypy, and pytest checks. Identify every healthcare- or life-sciences-specific
assumption before modifying code.

Then implement the ethanol port in the stages defined in PORTING_TO_ETHANOL.md. Use
the owner-approved ethanol identity, companies, benchmark, prompt, topic taxonomy,
visual scheme, schedule, and API credentials. Do not copy generated reports, strategy
archives, caches, state, logs, docs output, or credentials from the healthcare project.

Keep OPENAI_API_KEY and MASSIVE_API_KEY as the runtime environment-variable interface
unless the deployment architecture requires otherwise. Never display or copy secret
values.

Do not make a paid OpenAI request until configuration validation, Ruff, mypy, pytest,
strategy dry-run, and fixture-based site generation all pass. Before the first paid
request, show the assembled prompt metadata, history dates, report window, expected
heading, selected model, reasoning effort, and planned output paths.

If ethanol requires commodity or government datasets beyond public-equity market data,
stop and specify the proposed provider, data contract, cache, status handling, and tests
before implementing it. Do not disguise non-equity data as equity tickers.

After one controlled live run, verify the report content, citations, source status,
usage and cost log, idempotent same-date behavior, cached OpenAI fallback, site pages,
topic index, and PDF/HTML downloads. Report exactly what changed, what was tested, any
remaining domain decisions, and how to run and deploy the application.
```

## Handoff discipline

The receiving LLM should maintain a short migration log containing:

- Decisions made and their rationale.
- Files changed in each stage.
- Tests run and their results.
- Any deliberate deviations from this application.
- New providers or schemas introduced.
- Remaining owner decisions.
- Whether a paid API call has occurred and its estimated cost.

No deviation from a reliability invariant should be made silently.
