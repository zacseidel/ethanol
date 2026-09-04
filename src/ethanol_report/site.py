from __future__ import annotations

import hashlib
import html
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

import markdown
from bs4 import BeautifulSoup

from .config import ProjectConfig
from .render import report_html_name
from .storage import atomic_replace_directory, read_json, write_json

SITE_TITLE = "Ethanol Strategy Digest"

SITE_CSS = """
:root { --site-navy:#1e2422; --site-blue:#5a6360; --site-gold:#c9a24a;
  --site-ink:#1e2422; --site-muted:#5a6360; --site-line:#d4cfc4; --site-paper:#fffdf8;
  --site-panel:#e7e4dc; --site-header:#fffdf8; }
@import url("https://fonts.googleapis.com/css2?family=Source+Sans+3:ital,wght@0,400;0,600;0,700;1,400&family=Zilla+Slab:wght@600;700&display=swap");
.public-site-header { position:relative; z-index:20; color:var(--site-ink); background:var(--site-header);
  border-bottom:1px solid var(--site-line); box-shadow:0 1px 8px #1832480d; }
.public-site-header-inner { width:min(1500px,100%); min-height:60px; margin:0 auto;
  padding:.55rem 1.5rem; display:flex; align-items:center; justify-content:space-between; gap:1.5rem; }
.public-site-brand { color:#1e2422 !important;
  font:700 1.15rem/1.2 "Zilla Slab",Georgia,serif;
  text-decoration:none; letter-spacing:.015em; }
.public-site-nav { display:flex; align-items:center; gap:.25rem; flex-wrap:wrap; }
.public-site-nav a { color:#526879 !important; padding:.45rem .68rem; border-radius:4px;
  font:700 .78rem/1.2 "Source Sans 3",sans-serif; letter-spacing:.12em; text-transform:uppercase; text-decoration:none; }
.public-site-nav a:hover,.public-site-nav a[aria-current="page"] { color:#b33c28 !important;
  background:#e7e4dc; }
.public-page-body { margin:0; color:var(--site-ink); background:#f6f3ec;
  font:16px/1.62 "Source Sans 3",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.public-page { width:min(1040px,calc(100% - 2rem)); min-height:calc(100vh - 60px); margin:0 auto;
  padding:3rem clamp(1.25rem,4vw,4rem) 5rem; background:var(--site-paper);
  box-shadow:0 8px 30px #18324814; }
.public-page h1,.public-page h2,.public-page h3 { color:var(--site-navy);
  font-family:"Zilla Slab",Georgia,serif; line-height:1.2; }
.public-page h1 { margin:.15rem 0 1rem; font-size:clamp(2.05rem,5vw,3.25rem);
  font-weight:500; letter-spacing:-.025em; }
.public-page h2 { margin-top:2.2rem; padding-bottom:.35rem; border-bottom:2px solid var(--site-line); }
.public-page a { color:#b33c28; text-underline-offset:2px; }
.public-site-header + .page-shell { padding-top:1.25rem; }
.public-site-header + .page-shell main { border-top:1px solid var(--site-line); }
.public-site-header + .page-shell main > h1 { color:#1e2422;
  font-family:"Zilla Slab",Georgia,serif;
  font-size:clamp(2rem,4vw,2.75rem); font-weight:500; letter-spacing:-.035em; }
.public-site-header + .page-shell .report-nav { border-top:2px solid #9fb7c7; }
.site-eyebrow { margin:0; color:var(--site-blue); font-size:.77rem; font-weight:800;
  letter-spacing:.13em; text-transform:uppercase; }
.site-lede { max-width:740px; color:#40505e; font-size:1.13rem; }
.report-list { list-style:none; margin:2rem 0 0; padding:0; border-top:1px solid var(--site-line); }
.report-group { margin-top:2.5rem; }
.report-group h2 { margin:0; padding-bottom:.45rem; color:var(--site-navy);
  border-bottom:2px solid var(--site-line); font:700 1.45rem/1.2 "Zilla Slab",Georgia,serif; }
.report-group .report-list { margin-top:0; }
.report-list li { display:flex; align-items:center; gap:.75rem; border-bottom:1px solid var(--site-line); }
.report-list .report-list-link { min-width:0; flex:1; display:grid;
  grid-template-columns:minmax(190px,1fr) minmax(150px,.8fr) auto;
  gap:1rem; align-items:center; padding:1rem .2rem; color:inherit; text-decoration:none; }
.report-list li:hover { background:var(--site-panel); }
.report-list strong { color:var(--site-navy); font:700 1.06rem/1.3 "Zilla Slab",Georgia,serif; }
.report-list span { color:var(--site-muted); font-size:.9rem; }
.site-badge { display:inline-block; justify-self:end; padding:.18rem .5rem; border-radius:2px;
  color:#fffdf8 !important; background:#b33c28; font-size:.72rem !important; font-weight:800; text-transform:uppercase; }
.site-badge-warning { color:#754b05 !important; background:#fff0c9; }
.index-week { margin-top:2.5rem; }
.index-week > h2 { margin-bottom:.3rem; }
.index-report { margin:1.25rem 0 2rem; padding:1.1rem 1.25rem; border:1px solid var(--site-line);
  border-radius:5px; background:#fbfcfd; }
.index-report-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
.index-report h3 { margin:0 0 .8rem; font-size:1.22rem; }
.index-report h4 { margin:1rem 0 .35rem; color:var(--site-blue); font-size:.82rem;
  letter-spacing:.09em; text-transform:uppercase; }
.index-links { margin:.35rem 0 .6rem; padding-left:1.3rem; }
.index-links li { margin:.35rem 0; }
.topic-directory { margin-top:3.5rem; padding-top:.5rem; border-top:4px solid var(--site-gold); }
.topic-group { margin-top:2.5rem; }
.topic-section { margin:1.35rem 0; }
.topic-section h3 { margin-bottom:.4rem; }
.topic-links { list-style:none; margin:.35rem 0 0; padding:0; }
.topic-links li { padding:.65rem 0; border-bottom:1px solid var(--site-line); }
.topic-links span { display:block; margin-top:.15rem; color:var(--site-muted); font-size:.82rem; }
.index-empty { color:var(--site-muted); font-style:italic; }
.report-downloads { display:flex; align-items:center; gap:.42rem; flex-wrap:wrap; margin:.8rem 0 1.35rem; }
.report-downloads-compact { flex:0 0 auto; margin:0; }
.report-download-label { margin-right:.15rem; color:var(--site-muted); font-size:.78rem; font-weight:600; }
.download-button { display:inline-flex; align-items:center; justify-content:center; min-width:3.25rem;
  padding:.36rem .62rem; border:1px solid #b7c8d3; border-radius:4px; color:#315b75 !important;
  background:#fff; font:600 .76rem/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  letter-spacing:.025em; text-decoration:none !important; }
.download-button:hover { border-color:#7193a8; background:#edf4f7; }
.report-list-actions { padding-right:.2rem; }
.public-site-footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--site-line);
  color:var(--site-muted); font-size:.84rem; }
@media (max-width:700px) {
  .public-site-header-inner { align-items:flex-start; flex-direction:column; gap:.45rem; }
  .public-site-nav { margin-left:-.7rem; }
  .public-page { width:100%; }
  .report-list li { display:block; padding-bottom:.8rem; }
  .report-list .report-list-link { grid-template-columns:1fr; gap:.2rem; padding-bottom:.45rem; }
  .report-list-actions { padding:0 .2rem; }
  .index-report-heading { display:block; }
  .report-downloads-compact { margin:.2rem 0 .8rem; }
  .site-badge { justify-self:start; margin-top:.25rem; }
}
"""


@dataclass(frozen=True)
class SiteReport:
    report_date: date
    report_type: str
    report_name: str
    market_data_as_of: str
    quality: str
    source: Path
    archive_path: str


@dataclass(frozen=True)
class IndexedHeadline:
    report: SiteReport
    label: str
    fragment: str


@dataclass(frozen=True)
class IndexedEarningsCall:
    report: SiteReport
    label: str
    fragment: str


TOPIC_GROUPS = (
    (
        "Markets & Margins",
        (
            ("ethanol-prices", "Ethanol Prices", (r"\bethanol prices?\b", r"\bE10\b", r"\bE15\b", r"\bE85\b", r"\bblend(?:ing)? (?:demand|margin)")),
            ("corn-feedstocks", "Corn and Feedstocks", (r"\bcorn\b", r"\bfeedstocks?\b", r"\bbushels?\b", r"\bWASDE\b", r"\bacreage\b", r"\byields?\b")),
            ("energy-natural-gas", "Energy and Natural Gas", (r"\bnatural gas\b", r"\bnatgas\b", r"\bcrude\b", r"\bgasoline\b", r"\bWTI\b", r"\bBrent\b")),
            ("rins-policy-credits", "RINs and Policy Credits", (r"\bRINs?\b", r"\bD6\b", r"\bLCFS\b", r"\b45Z\b", r"\b45Q\b", r"\bGREET\b")),
            ("crush-margins", "Crush Margins", (r"\bcrush\b", r"\bplant margins?\b", r"\boperating margins?\b", r"\bDDGS\b", r"\bcorn oil\b")),
        ),
    ),
    (
        "Operations & Supply",
        (
            ("production-capacity", "Production and Capacity", (r"\bproduction\b", r"\bcapacity\b", r"\butilization\b", r"\bbiorefiner")),
            ("inventories-blending", "Inventories and Blending", (r"\binventor", r"\bstocks?\b", r"\bblend(?:ing|ers?)\b")),
            ("plant-outages", "Plant Outages and Maintenance", (r"\boutages?\b", r"\bmaintenance\b", r"\bidled\b", r"\bshutdown")),
            ("logistics-rail", "Logistics and Rail", (r"\brail\b", r"\btank cars?\b", r"\bbarge\b", r"\bfreight\b", r"\bUnion Pacific\b", r"\bCSX\b")),
            ("exports", "Exports", (r"\bexports?\b", r"\bGulf\b", r"\bBrazil\b", r"\bUNICA\b")),
        ),
    ),
    (
        "Companies & Capital",
        (
            ("company-strategy", "Company Strategy", (r"\bGreen Plains\b", r"\bValero\b", r"\bADM\b", r"\bPOET\b", r"\bAndersons\b", r"\bstrategy\b")),
            ("earnings", "Earnings", (r"\bearnings\b", r"\bguidance\b", r"\b10-K\b", r"\b10-Q\b")),
            ("ma-partnerships", "M&A and Partnerships", (r"\bacqui", r"\bmerger\b", r"\bpartnership\b", r"\bjoint venture\b")),
            ("capital-projects", "Capital Projects", (r"\bcapital project", r"\bexpansion\b", r"\bCCS\b", r"\bcarbon capture\b")),
            ("balance-sheets", "Balance Sheets and Financing", (r"\bbalance sheet\b", r"\bfinancing\b", r"\bdebt\b", r"\bdividend\b")),
        ),
    ),
    (
        "Policy & Technology",
        (
            ("rfs", "Renewable Fuel Standard", (r"\bRFS\b", r"\bRVO\b", r"\bsmall-refinery\b", r"\bSRE\b")),
            ("tax-credits", "Tax Credits and Regulation", (r"\btax credit", r"\bIRA\b", r"\bTreasury\b", r"\bEPA\b")),
            ("carbon-capture", "Carbon Capture", (r"\bcarbon capture\b", r"\bCCS\b", r"\b45Q\b", r"\bSummit Carbon\b")),
            ("saf", "Sustainable Aviation Fuel", (r"\bSAF\b", r"\balcohol-to-jet\b", r"\bATJ\b", r"\bNeste\b")),
            ("lcfs", "Low-Carbon Fuel Standards", (r"\bLCFS\b", r"\blow-carbon\b", r"\bcarbon intensity\b")),
            ("other", "Other", ()),
        ),
    ),
)


def _long_date(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _discover_reports(config: ProjectConfig) -> list[SiteReport]:
    final_root = config.root / "reports" / "final"
    reports: list[SiteReport] = []
    if not final_root.is_dir():
        return reports

    def add_folder(folder: Path, archive_path: str) -> None:
        try:
            published = date.fromisoformat(folder.name)
        except ValueError:
            return
        manifest = read_json(folder / "manifest.json", {})
        if not isinstance(manifest, dict):
            return
        report_name = str(manifest.get("report_name") or "").strip()
        if not report_name:
            report_name = config.report_name
        source = folder / f"{report_name}-{published.isoformat()}.html"
        if not source.is_file():
            fallback = folder / report_html_name(published, config)
            if fallback.is_file():
                source = fallback
            else:
                return
        reports.append(
            SiteReport(
                report_date=published,
                report_type=str(manifest.get("report_type") or "ethanol"),
                report_name=report_name,
                market_data_as_of=str(manifest.get("market_data_as_of") or ""),
                quality=str(manifest.get("quality") or "unknown"),
                source=source,
                archive_path=archive_path,
            )
        )

    for folder in final_root.iterdir():
        if not folder.is_dir():
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder.name):
            add_folder(folder, folder.name)
            continue
        for report_folder in folder.iterdir():
            if report_folder.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_folder.name):
                add_folder(report_folder, f"{folder.name}/{report_folder.name}")
    return sorted(
        reports,
        key=lambda item: (item.report_date, item.report_type),
        reverse=True,
    )


def _homepage_report(reports: list[SiteReport]) -> SiteReport | None:
    farmer_reports = [report for report in reports if report.report_type == "farmer"]
    if farmer_reports:
        return farmer_reports[0]
    ethanol_reports = [report for report in reports if report.report_type == "ethanol"]
    return ethanol_reports[0] if ethanol_reports else None


def _site_header(prefix: str, active: str) -> str:
    home = prefix or "./"
    items = (
        ("latest", "Latest report", home),
        ("news", "News & Earnings", f"{prefix}news/"),
        ("reports", "Past reports", f"{prefix}reports/"),
        ("about", "About", f"{prefix}about/"),
        ("methodology", "Methodology", f"{prefix}methodology/"),
    )
    links = "".join(
        f'<a href="{href}"{_current_page(key == active)}>{html.escape(label)}</a>'
        for key, label, href in items
    )
    return (
        '<header class="public-site-header"><div class="public-site-header-inner">'
        f'<a class="public-site-brand" href="{home}">{html.escape(SITE_TITLE)}</a>'
        f'<nav class="public-site-nav" aria-label="Website navigation">{links}</nav>'
        "</div></header>"
    )


def _current_page(active: bool) -> str:
    return ' aria-current="page"' if active else ""


def _download_name(report: SiteReport, extension: str) -> str:
    return f"{report.source.stem}.{extension}"


def _report_download_links(
    report: SiteReport,
    href_prefix: str,
    *,
    compact: bool = False,
) -> str:
    classes = "report-downloads report-downloads-compact" if compact else "report-downloads"
    label = "" if compact else '<span class="report-download-label">Download report</span>'
    pdf_href = href_prefix + quote(_download_name(report, "pdf"))
    html_href = href_prefix + quote(_download_name(report, "html"))
    report_label = html.escape(f"{report.report_name} for {_long_date(report.report_date)}")
    return (
        f'<div class="{classes}" aria-label="Download {report_label}">{label}'
        f'<a class="download-button" href="{html.escape(pdf_href, quote=True)}" download>PDF</a>'
        f'<a class="download-button" href="{html.escape(html_href, quote=True)}" download>HTML</a>'
        "</div>"
    )


def _decorate_report(
    source: Path,
    destination: Path,
    *,
    prefix: str,
    active: str,
    report: SiteReport | None = None,
    download_prefix: str = "",
) -> None:
    soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
    if soup.head is None or soup.body is None:
        raise RuntimeError(f"Cannot publish malformed report HTML: {source}")
    # Publishing can be rerun against an already decorated artifact. Strip
    # wrapper chrome first so the report cannot acquire nested headers or
    # repeated sidebars over successive site builds.
    for existing in soup.select("header.public-site-header"):
        existing.decompose()
    for existing in soup.select(".report-downloads-page"):
        existing.decompose()
    report_navs = soup.select("nav.report-nav")
    for duplicate in report_navs[1:]:
        duplicate.decompose()
    styles = soup.new_tag("style")
    styles.string = SITE_CSS
    soup.head.append(styles)
    header = BeautifulSoup(_site_header(prefix, active), "html.parser")
    soup.body.insert(0, header)
    if report is not None:
        main = soup.select_one("main")
        title = main.find("h1") if main else None
        if title is not None:
            controls = BeautifulSoup(
                _report_download_links(report, download_prefix),
                "html.parser",
            ).div
            if controls is not None:
                controls["class"] = "report-downloads report-downloads-page"
                title.insert_after(controls)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(str(soup), encoding="utf-8")


def _page_document(title: str, body: str, *, prefix: str, active: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)} · {html.escape(SITE_TITLE)}</title>"
        f"<style>{SITE_CSS}</style></head>"
        f'<body class="public-page-body">{_site_header(prefix, active)}'
        f'<main class="public-page">{body}'
        f'<footer class="public-site-footer">{html.escape(SITE_TITLE)} uses public market and '
        "company information. It is informational and is not investment advice.</footer>"
        "</main></body></html>"
    )


def _content_page(config: ProjectConfig, name: str, *, prefix: str) -> str:
    path = config.root / "site_content" / f"{name}.md"
    if not path.is_file():
        raise RuntimeError(f"Missing public site content: {path}")
    body = markdown.markdown(path.read_text(encoding="utf-8"), extensions=["tables"])
    return _page_document(name.title(), body, prefix=prefix, active=name)


def _archive_page(reports: list[SiteReport]) -> str:
    groups = (
        ("ethanol", "Weekly Corn and Ethanol Intel Report"),
        ("farmer", "Farmer Corn Brief"),
    )
    sections: list[str] = []
    for report_type, heading in groups:
        group_reports = [report for report in reports if report.report_type == report_type]
        rows: list[str] = []
        for index, report in enumerate(group_reports):
            market_date = ""
            if report.market_data_as_of:
                try:
                    market_date = _long_date(date.fromisoformat(report.market_data_as_of))
                except ValueError:
                    market_date = report.market_data_as_of
            # Archive entries are historical publications. Their data-quality
            # state is preserved in each report's manifest, but should not
            # turn the archive into a warning dashboard.
            badge = "Latest" if index == 0 else "Final"
            badge_class = ""
            through_label = (
                "Nearby corn through" if report.report_type == "farmer" else "Market data through"
            )
            rows.append(
                f'<li class="report-list-item"><a class="report-list-link" href="{report.archive_path}/">'
                f"<strong>{_long_date(report.report_date)}</strong>"
                f"<span>{through_label} {html.escape(market_date or 'not recorded')}</span>"
                f'<span class="site-badge {badge_class}">{badge}</span></a>'
                f'<div class="report-list-actions">{_report_download_links(report, f"{report.archive_path}/", compact=True)}</div>'
                "</li>"
            )
        listing = "".join(rows) or '<li class="report-empty">No reports published yet.</li>'
        sections.append(
            f'<section class="report-group"><h2>{heading}</h2>'
            f'<ul class="report-list">{listing}</ul></section>'
        )
    listing = "".join(sections) or "<p>No final reports have been published yet.</p>"
    body = (
        '<p class="site-eyebrow">Archive</p><h1>Past reports</h1>'
        '<p class="site-lede">Browse the complete set of published weekly reports. '
        'Each report preserves the market data, earnings context, and strategy narrative '
        'available when it was produced.</p>'
        f"{listing}"
    )
    return _page_document("Past reports", body, prefix="../", active="reports")


def _indexed_report_content(
    report: SiteReport,
) -> tuple[list[IndexedHeadline], list[IndexedEarningsCall]]:
    soup = BeautifulSoup(report.source.read_text(encoding="utf-8"), "html.parser")
    headlines: list[IndexedHeadline] = []
    seen_headlines: set[str] = set()
    for link in soup.select('nav.strategy-narrative-links a[href^="#"]'):
        fragment = str(link.get("href") or "").removeprefix("#")
        label = link.get_text(" ", strip=True)
        if fragment and label and fragment not in seen_headlines:
            headlines.append(IndexedHeadline(report, label, fragment))
            seen_headlines.add(fragment)
    earnings_calls: list[IndexedEarningsCall] = []
    seen_earnings: set[str] = set()
    earnings_links = soup.select('ul.section-jump-list a[href^="#earnings-"]')
    if not earnings_links:
        earnings_links = soup.select('nav.report-nav a[href^="#earnings-"]')
    for link in earnings_links:
        fragment = str(link.get("href") or "").removeprefix("#")
        label = link.get_text(" ", strip=True)
        if fragment and label and fragment not in seen_earnings:
            earnings_calls.append(IndexedEarningsCall(report, label, fragment))
            seen_earnings.add(fragment)
    return headlines, earnings_calls


def _topic_slugs(headline: IndexedHeadline) -> tuple[str, ...]:
    text = headline.label.casefold()
    matches: list[str] = []
    for _group_label, topics in TOPIC_GROUPS:
        for slug, _topic_label, patterns in topics:
            if slug == "other":
                continue
            if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
                matches.append(slug)
    return tuple(dict.fromkeys(matches)) if matches else ("other",)


def _indexed_href(report: SiteReport, fragment: str = "") -> str:
    suffix = f"#{fragment}" if fragment else ""
    return f"../reports/{report.archive_path}/{suffix}"


def _index_link_list(items: list[IndexedHeadline] | list[IndexedEarningsCall]) -> str:
    if not items:
        return '<p class="index-empty">None in this report.</p>'
    return '<ul class="index-links">' + "".join(
        f'<li><a href="{html.escape(_indexed_href(item.report, item.fragment), quote=True)}">'
        f"{html.escape(item.label)}</a></li>"
        for item in items
    ) + "</ul>"


def _news_index_page(reports: list[SiteReport]) -> str:
    news_reports = [report for report in reports if report.report_type == "ethanol"]
    indexed = [(report, *_indexed_report_content(report)) for report in news_reports]
    dates = sorted({report.report_date for report in news_reports}, reverse=True)
    weeks: list[str] = []
    for report_date in dates:
        report_cards: list[str] = []
        for report, headlines, earnings_calls in indexed:
            if report.report_date != report_date:
                continue
            report_cards.append(
                '<article class="index-report">'
                '<div class="index-report-heading">'
                f'<h3><a href="{html.escape(_indexed_href(report), quote=True)}">'
                f"{html.escape(report.report_name)}</a></h3>"
                f'{_report_download_links(report, f"../reports/{report.archive_path}/", compact=True)}'
                "</div>"
                f"<h4>Strategy Narrative</h4>{_index_link_list(headlines)}"
                f"<h4>Earnings Calls</h4>{_index_link_list(earnings_calls)}"
                "</article>"
            )
        weeks.append(
            f'<section class="index-week"><h2>{_long_date(report_date)}</h2>'
            + "".join(report_cards)
            + "</section>"
        )
    if not weeks:
        weeks.append('<p class="index-empty">No published reports are available to index.</p>')

    all_headlines = [headline for _report, headlines, _earnings in indexed for headline in headlines]
    topic_sections: list[str] = []
    for group_label, topics in TOPIC_GROUPS:
        rendered_topics: list[str] = []
        for slug, topic_label, _patterns in topics:
            matches = [headline for headline in all_headlines if slug in _topic_slugs(headline)]
            listing = '<ul class="topic-links">' + "".join(
                f'<li><a href="{html.escape(_indexed_href(item.report, item.fragment), quote=True)}">'
                f"{html.escape(item.label)}</a>"
                f"<span>{_long_date(item.report.report_date)} · "
                f"{html.escape(item.report.report_name)}</span></li>"
                for item in matches
            ) + "</ul>"
            if not matches:
                listing = '<p class="index-empty">No indexed headlines.</p>'
            rendered_topics.append(
                f'<section class="topic-section" id="topic-{slug}"><h3>{topic_label}</h3>'
                f"{listing}</section>"
            )
        topic_sections.append(
            f'<section class="topic-group"><h2>{group_label}</h2>'
            + "".join(rendered_topics)
            + "</section>"
        )

    body = (
        '<p class="site-eyebrow">Intelligence library</p><h1>News &amp; Earnings Index</h1>'
        '<p class="site-lede">Browse weekly news headlines and earnings-call coverage, then '
        'review news across the business topics it affects.</p>'
        '<section aria-labelledby="weekly-index-heading"><h2 id="weekly-index-heading">By week</h2>'
        + "".join(weeks)
        + '</section><section class="topic-directory" aria-labelledby="topic-index-heading">'
        '<p class="site-eyebrow">Business topics</p><h2 id="topic-index-heading">By topic</h2>'
        + "".join(topic_sections)
        + "</section>"
    )
    return _page_document("News & Earnings Index", body, prefix="../", active="news")


def _empty_home(config: ProjectConfig) -> str:
    name = html.escape(str(config.settings["report"]["name"]))
    body = (
        f'<p class="site-eyebrow">Weekly intelligence</p><h1>{name}</h1>'
        '<p class="site-lede">The first public report has not been published yet. '
        'Visit the archive after the next report run.</p>'
    )
    return _page_document(name, body, prefix="", active="latest")


def _copy_assets(report_html: Path, destination_folder: Path) -> None:
    if 'src="assets/' not in report_html.read_text(encoding="utf-8"):
        return
    source = report_html.parent / "assets"
    if source.is_dir():
        shutil.copytree(source, destination_folder / "assets")


def _publish_report_downloads(
    reports: list[SiteReport],
    destination: Path,
    previous_site: Path | None = None,
) -> None:
    if not reports:
        return
    previous_manifest = read_json(previous_site / ".download-manifest.json", {}) if previous_site else {}
    previous_hashes = (
        previous_manifest.get("reports", {}) if isinstance(previous_manifest, dict) else {}
    )
    previous_hashes = previous_hashes if isinstance(previous_hashes, dict) else {}
    current_hashes: dict[str, str] = {}
    pending: list[tuple[SiteReport, Path]] = []

    for report in reports:
        folder = destination / "reports" / report.archive_path
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report.source, folder / _download_name(report, "html"))
        fingerprint = hashlib.sha256(report.source.read_bytes()).hexdigest()
        current_hashes[report.archive_path] = fingerprint
        old_pdf = (
            previous_site / "reports" / report.archive_path / _download_name(report, "pdf")
            if previous_site
            else None
        )
        fingerprint_matches = previous_hashes.get(report.archive_path) == fingerprint
        migration_cache = not previous_hashes and old_pdf is not None and old_pdf.is_file()
        if old_pdf is not None and old_pdf.is_file() and (fingerprint_matches or migration_cache):
            shutil.copy2(old_pdf, folder / _download_name(report, "pdf"))
        else:
            pending.append((report, folder))

    if pending:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is required to generate report PDFs") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.emulate_media(media="print")
                for report, folder in pending:
                    page.set_content(report.source.read_text(encoding="utf-8"), wait_until="load")
                    page.evaluate("document.fonts.ready")
                    page.pdf(
                        path=str(folder / _download_name(report, "pdf")),
                        format="Letter",
                        print_background=True,
                        margin={
                            "top": "0.45in",
                            "right": "0.45in",
                            "bottom": "0.45in",
                            "left": "0.45in",
                        },
                    )
            finally:
                browser.close()

    write_json(
        destination / ".download-manifest.json",
        {"schema": 1, "reports": current_hashes},
    )


def build_site(config: ProjectConfig, output: Path | None = None) -> dict[str, Any]:
    destination = (output or config.root / "docs").resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        reports = _discover_reports(config)
        (temporary / ".nojekyll").write_text("", encoding="utf-8")
        (temporary / "reports").mkdir()
        (temporary / "reports" / "index.html").write_text(
            _archive_page(reports), encoding="utf-8"
        )
        (temporary / "news").mkdir()
        (temporary / "news" / "index.html").write_text(
            _news_index_page(reports), encoding="utf-8"
        )
        for name in ("about", "methodology"):
            folder = temporary / name
            folder.mkdir()
            (folder / "index.html").write_text(
                _content_page(config, name, prefix="../"), encoding="utf-8"
            )
        latest = _homepage_report(reports)
        if latest is None:
            (temporary / "index.html").write_text(_empty_home(config), encoding="utf-8")
        else:
            _decorate_report(
                latest.source,
                temporary / "index.html",
                prefix="",
                active="latest",
                report=latest,
                download_prefix=f"reports/{latest.archive_path}/",
            )
            _copy_assets(latest.source, temporary)
        for report in reports:
            folder = temporary / "reports" / report.archive_path
            prefix = "../" * (len(report.archive_path.split("/")) + 1)
            _decorate_report(
                report.source,
                folder / "index.html",
                prefix=prefix,
                active="reports",
                report=report,
            )
            _copy_assets(report.source, folder)
        if reports:
            _publish_report_downloads(
                reports, temporary, destination if destination.is_dir() else None
            )
        atomic_replace_directory(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "status": "ok",
        "output": str(destination),
        "reports": len(reports),
        "latest_report": latest.report_date.isoformat() if latest else None,
    }
