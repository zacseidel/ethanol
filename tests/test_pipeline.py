from __future__ import annotations

import json
from datetime import date, timedelta

from bs4 import BeautifulSoup

from ethanol_report.cache import MarketCache
from ethanol_report.pipeline import export_standalone_report, rerender_report, run_report
from ethanol_report.render import _presentation_narrative
from ethanol_report.storage import config_hash, read_gzip_json, write_gzip_json


class FakeMassive:
    def __init__(self, config):
        self.config = config
        self.cache = MarketCache(config)

    def close(self):
        return None

    def company(self, ticker):
        index = list(self.config.universe.companies).index(ticker) + 1
        value = {
            "ticker": ticker,
            "market_cap": index * 1_000_000_000,
            "exchange": "XNYS",
            "description": f"Provider description for {ticker}.",
        }
        self.cache.save_company(ticker, value)
        return value

    def prices(self, ticker, start, end):
        index = list(self.config.universe.companies).index(ticker) + 1 if ticker != "SPY" else 1
        rows = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                rows.append(
                    {"date": current, "close": 80 + index * 3 + (current - start).days * index / 50}
                )
            current += timedelta(days=1)
        self.cache.save_prices(
            ticker,
            {
                "covered_start": start.isoformat(),
                "covered_end": end.isoformat(),
                "bars": rows,
            },
        )
        return rows


class FakeBrowser:
    entered = 0

    def __init__(self):
        self.page = object()

    def __enter__(self):
        type(self).entered += 1
        return self

    def __exit__(self, *_):
        return None

    def html(self, url, wait_ms=2500):
        if "chatgpt.com" in url:
            return """
            <div data-message-author-role="assistant"><div class="markdown">
            <h1>Strategy Brief</h1><p><strong>Week of August 3, 2026</strong></p>
            <h2>Executive readout</h2>
            <h3>1. Cloud strategy headline</h3><p>Cloud fixture narrative.</p>
            <h2>Functional strategy summary</h2><p>Remove this section.</p>
            <h2>Bottom line</h2><p>Keep this section.</p>
            </div></div>
            """
        return """
        <html><body><div>Last report Jul 30, 2026</div><div>Next earnings Oct 28, 2026</div>
        <div><span>Call transcript</span><p>summarize_auto Fixture earnings summary.</p></div>
        <section><h2>At a glance</h2><div class="sgb2mf">
        <strong class="mFa7Bd">Guidance:</strong><span class="KBDbl">Guidance increased.</span>
        </div></section>
        <div class="B1GkSe"><span class="tDiKLc">Strong results</span>
        <span class="kcbpeb">5m 44.75999999999999s</span>
        <span class="h3qzgf">Management raised guidance.</span></div>
        </body></html>
        """


def test_strategy_narrative_links_support_html_headings_and_strip_delta_labels():
    body = """
<h3>1. NEW / RESOLVE — First development</h3>
<p>First detail.</p>
<h3>2. CONFIRM — Second development</h3>
<p>Second detail.</p>
"""
    presented = _presentation_narrative(body)
    soup = BeautifulSoup(presented, "html.parser")
    links = soup.select("nav.strategy-narrative-links a")
    assert [link.get_text(" ", strip=True) for link in links] == [
        "1. First development",
        "2. Second development",
    ]
    assert "NEW / RESOLVE" not in presented
    assert "CONFIRM" not in presented


def test_strategy_jump_list_uses_interpretive_headlines_not_form_sections():
    from ethanol_report.narrative import _embedded_strategy_body

    raw = """# Ethanol Strategy Brief
## Week of August 13, 2026

## Executive View
- Takeaway one.

## 1. Lower yield matters more than the headline crop increase
**What happened**
USDA cut yield.

## 2. Ethanol supply is testing demand capacity
**What happened**
Stocks rose.

## Bottom Line
Watch inventories.
"""
    presented = _presentation_narrative(_embedded_strategy_body(raw))
    soup = BeautifulSoup(presented, "html.parser")
    labels = [link.get_text(" ", strip=True) for link in soup.select("nav.strategy-narrative-links a")]
    assert labels == [
        "1. Lower yield matters more than the headline crop increase",
        "2. Ethanol supply is testing demand capacity",
    ]
    assert soup.select_one("h3#executive-view") is not None
    assert soup.select_one("h3#bottom-line") is not None
    assert all("Executive view" not in label for label in labels)
    assert all("Risk dashboard" not in label for label in labels)


def test_end_to_end_report_and_baseline(project, monkeypatch):
    import ethanol_report.narrative as narrative_module
    import ethanol_report.pipeline as pipeline

    monkeypatch.setattr(pipeline, "MassiveClient", FakeMassive)
    monkeypatch.setattr(pipeline, "BrowserSession", FakeBrowser)

    def generate_fixture_strategy(_config, report_date, *, force=False, **_kwargs):
        return {
            "report_date": report_date.isoformat(),
            "generated_at": f"{report_date.isoformat()}T12:00:00Z",
            "model": "gpt-5.6-sol",
            "response_id": "resp_fixture",
            "prompt_sha256": "fixture",
            "usage": {},
            "estimated_cost_usd": 0.0,
            "content_markdown": """# Ethanol Strategy Brief
## Week of August 3, 2026

## Executive readout

| Exposure | Main driver |
| --- | --- |
| Corn | Central Corn Belt rain |

### 1. Cloud strategy headline
Cloud fixture narrative.

## Functional strategy summary
Remove this section.

## Bottom line
Keep this section.
""",
        }

    monkeypatch.setattr(narrative_module, "generate_strategy_report", generate_fixture_strategy)
    FakeBrowser.entered = 0
    actual_render_earnings_charts = pipeline.render_earnings_charts
    requested_earnings_charts: list[list[str]] = []

    def render_sample_earnings_charts(folder, config, report_date, bars, tickers):
        requested_earnings_charts.append(tickers)
        return actual_render_earnings_charts(folder, config, report_date, bars, tickers[:2])

    monkeypatch.setattr(pipeline, "render_earnings_charts", render_sample_earnings_charts)
    first = run_report(project, date(2026, 8, 3))
    assert first["baseline"] is None
    assert first["market_data_as_of"] == "2026-07-31"
    first_folder = project.root / "reports" / "final" / "2026-08-03"
    html_name = "Weekly Corn and Ethanol Intel Report-2026-08-03.html"
    for name in (
        html_name,
        "report.md",
        "snapshot.csv",
        "changes.csv",
        "render-data.json.gz",
        "manifest.json",
    ):
        assert (first_folder / name).stat().st_size > 0
    report_html = (first_folder / html_name).read_text()
    assert "data:image/webp;base64" in report_html
    assert 'src="assets/' not in report_html
    assert 'class="report-nav"' in report_html
    assert "Zilla Slab" in report_html
    assert "Week of August 3, 2026" in report_html
    assert "Narrative created:" in report_html
    assert "Strategy brief for" not in report_html
    assert "Functional strategy summary" not in report_html
    assert "Remove this section" not in report_html
    assert "Keep this section" in report_html
    assert 'class="sortable"' in report_html
    assert "3m rank" not in report_html
    assert "12m rank" not in report_html
    assert "24m rank" not in report_html
    assert 'href="#company-' in report_html
    assert 'href="#earnings-' in report_html
    assert 'href="#news-' not in report_html
    assert 'class="section-jump-list"' in report_html
    assert 'class="strategy-narrative-links"' in report_html
    assert 'href="#strategy-executive-1-cloud-strategy-headline"' in report_html
    assert "summarize_auto" not in report_html
    assert report_html.index("At a Glance") < report_html.index("Key Moments from the Call")
    assert ">Weekly Corn and Ethanol Intel Report<" in report_html
    assert "5m — Strong results" in report_html
    assert "44.759" not in report_html
    assert "5m 44" not in report_html
    assert 'class="insight-card"' not in report_html
    assert "Google Finance earnings page" in report_html
    assert "Recent Earnings Highlights — 3m Ret" in report_html
    assert "Selected News" not in report_html
    assert "Data Quality and Collection Status" not in report_html
    assert "Methodology" not in report_html
    assert "h2::after" not in report_html
    assert "border-bottom:3px solid var(--navy)" in report_html
    soup = BeautifulSoup(report_html, "html.parser")
    driver_heading = soup.find("th", string="Main driver")
    assert driver_heading is not None
    assert driver_heading.find_parent("div", class_="table-wrap") is not None
    strategy_heading = soup.select_one("h2#strategy-narrative")
    strategy_links = soup.select_one("nav.strategy-narrative-links")
    executive_heading = soup.select_one("h3#executive-readout")
    assert strategy_heading is not None
    assert strategy_links is not None
    assert executive_heading is not None
    tape = soup.select_one("div.commodity-tape")
    assert tape is not None
    assert "Nearby corn" in tape.get_text()
    assert "perception of yield and demand risk" in tape.get_text()
    assert "Nearby corn: $4.285/bu" in report_html
    assert "+$0.285" in report_html
    assert strategy_heading.find_next("nav") == strategy_links
    assert strategy_links.find_next_sibling("h3") == executive_heading
    strategy_link_labels = [link.get_text(" ", strip=True) for link in strategy_links.find_all("a")]
    assert strategy_link_labels == ["1. Cloud strategy headline"]
    report_images = soup.find_all("img")
    assert report_images
    assert all(
        str(image.get("src", "")).startswith("data:image/webp;base64,")
        for image in report_images
    )
    earnings_heading = soup.select_one("h2#recent-earnings-highlights-3m-ret")
    assert earnings_heading is not None
    first_earnings = earnings_heading.find_next_sibling("ul").find("li").get_text(" ", strip=True)
    last_ticker = list(project.universe.companies)[-1]
    last_name = project.universe.companies[last_ticker].name
    assert first_earnings.startswith(f"{last_name} ({last_ticker})")
    company_nav_links = soup.select('nav.report-nav li ul a[href^="#company-"]')
    assert len(company_nav_links) == len(project.universe.companies)
    company_headings = soup.select('h3[id^="earnings-"]')
    assert company_headings
    assert all("3m" not in heading.get_text(" ", strip=True) for heading in company_headings)
    assert all(
        heading.select_one('a[href^="#company-"]') is not None for heading in company_headings
    )
    assert soup.select('img[alt*="S&P 500"]')
    anchors = {str(item.get("id")) for item in soup.select("[id]")}
    fragment_links = [str(item["href"])[1:] for item in soup.select('a[href^="#"]')]
    assert fragment_links
    assert not (set(fragment_links) - anchors)
    markdown = (first_folder / "report.md").read_text()
    for category in project.universe.categories:
        assert category in markdown
    manifest = json.loads((first_folder / "manifest.json").read_text())
    assert html_name in manifest["files"]
    assert not [row for row in manifest["sources"] if row["source"] == "Massive news"]
    assert any(
        name.startswith("assets/earnings-") and name.endswith(".webp") for name in manifest["files"]
    )
    assert len(requested_earnings_charts[0]) == len(project.universe.companies)
    assert manifest["schema"] == 2
    assert manifest["configuration_sha256"] == config_hash(
            [
                project.root / "config" / "settings.yaml",
                project.root / "inputs" / "companies.md",
                project.root / "inputs" / "ethanol-strategy-prompt.md",
            ]
    )
    assert manifest["metrics"]["output_bytes"]["charts"] > 0
    assert manifest["metrics"]["price_retention"]["cutoff"]

    standalone_path = project.root / "standalone.html"
    standalone = export_standalone_report(project, date(2026, 8, 3), standalone_path)
    assert standalone["bytes"] == standalone_path.stat().st_size
    standalone_html = standalone_path.read_text()
    assert "data:image/webp;base64" in standalone_html
    assert 'src="assets/' not in standalone_html

    second = run_report(project, date(2026, 8, 10))
    assert second["baseline"] == "2026-08-03"
    changes = (project.root / "reports" / "final" / "2026-08-10" / "changes.csv").read_text()
    assert "category_performance" in changes
    assert "overall_stock" in changes
    assert "within_category" in changes

    # A same-date rerun replaces the same folder rather than creating a revision.
    rerun = run_report(project, date(2026, 8, 10))
    assert rerun["output"] == second["output"]
    assert not list((project.root / "reports" / "final").glob("2026-08-10-*"))
    assert FakeBrowser.entered == 1

    class NetworkMustNotRun:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("render-only mode attempted a network provider")

    monkeypatch.setattr(pipeline, "MassiveClient", NetworkMustNotRun)
    chart_requests_before_rerender = len(requested_earnings_charts)
    render_data_path = first_folder / "render-data.json.gz"
    render_data = read_gzip_json(render_data_path)
    render_data["recent_earnings"] = [
        row
        for row in render_data["recent_earnings"]
        if (first_folder / "assets" / f"earnings-{row['ticker'].lower()}-3m.webp").is_file()
    ]
    write_gzip_json(render_data_path, render_data)
    orphan_chart = first_folder / "assets" / "unused-chart.webp"
    orphan_chart.write_bytes(b"unused")
    (project.root / "state" / "earnings.json").write_text("{}\n")
    (project.root / "state" / "narrative.json").write_text("{}\n")
    rendered = rerender_report(project, date(2026, 8, 3))
    assert rendered["mode"] == "render-only"
    render_manifest = json.loads(
        (project.root / "reports" / "final" / "2026-08-03" / "manifest.json").read_text()
    )
    assert render_manifest["metrics"]["mode"] == "render-only"
    assert len(requested_earnings_charts) == chart_requests_before_rerender
    assert not orphan_chart.exists()
    faithful_html = (
        project.root
        / "reports"
        / "final"
        / "2026-08-03"
        / "Weekly Corn and Ethanol Intel Report-2026-08-03.html"
    ).read_text()
    assert "Fixture earnings summary" in faithful_html
    assert "Cloud fixture narrative" in faithful_html
