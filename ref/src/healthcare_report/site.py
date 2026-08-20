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

SITE_CSS = """
:root { --site-navy:#183e5a; --site-blue:#35647f; --site-gold:#d4a43c;
  --site-ink:#1d2935; --site-muted:#657482; --site-line:#d8e1e8; --site-paper:#fff;
  --site-panel:#f3f7f9; --site-header:#f7fafb; }
.public-site-header { position:relative; z-index:20; color:var(--site-ink); background:var(--site-header);
  border-bottom:1px solid var(--site-line); box-shadow:0 1px 8px #1832480d; }
.public-site-header-inner { width:min(1500px,100%); min-height:60px; margin:0 auto;
  padding:.55rem 1.5rem; display:flex; align-items:center; justify-content:space-between; gap:1.5rem; }
.public-site-brand { color:#294f69 !important;
  font:500 1rem/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  text-decoration:none; letter-spacing:.015em; }
.public-site-nav { display:flex; align-items:center; gap:.25rem; flex-wrap:wrap; }
.public-site-nav a { color:#526879 !important; padding:.45rem .68rem; border-radius:4px;
  font:500 .86rem/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; text-decoration:none; }
.public-site-nav a:hover,.public-site-nav a[aria-current="page"] { color:#214b68 !important;
  background:#e7eff4; }
.public-page-body { margin:0; color:var(--site-ink); background:#edf2f5;
  font:16px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.public-page { width:min(1040px,calc(100% - 2rem)); min-height:calc(100vh - 60px); margin:0 auto;
  padding:3rem clamp(1.25rem,4vw,4rem) 5rem; background:var(--site-paper);
  box-shadow:0 8px 30px #18324814; }
.public-page h1,.public-page h2,.public-page h3 { color:var(--site-navy);
  font-family:Georgia,"Times New Roman",serif; line-height:1.2; }
.public-page h1 { margin:.15rem 0 1rem; font-size:clamp(2.05rem,5vw,3.25rem);
  font-weight:500; letter-spacing:-.025em; }
.public-page h2 { margin-top:2.2rem; padding-bottom:.35rem; border-bottom:2px solid var(--site-line); }
.public-page a { color:#1269a0; text-underline-offset:2px; }
.public-site-header + .page-shell { padding-top:1.25rem; }
.public-site-header + .page-shell main { border-top:1px solid var(--site-line); }
.public-site-header + .page-shell main > h1 { color:#244b65;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:clamp(2rem,4vw,2.75rem); font-weight:500; letter-spacing:-.035em; }
.public-site-header + .page-shell .report-nav { border-top:2px solid #9fb7c7; }
.site-eyebrow { margin:0; color:var(--site-blue); font-size:.77rem; font-weight:800;
  letter-spacing:.13em; text-transform:uppercase; }
.site-lede { max-width:740px; color:#40505e; font-size:1.13rem; }
.report-list { list-style:none; margin:2rem 0 0; padding:0; border-top:1px solid var(--site-line); }
.report-group { margin-top:2.5rem; }
.report-group h2 { margin:0; padding-bottom:.45rem; color:var(--site-navy);
  border-bottom:2px solid var(--site-line); font:700 1.45rem/1.2 Georgia,"Times New Roman",serif; }
.report-group .report-list { margin-top:0; }
.report-list li { display:flex; align-items:center; gap:.75rem; border-bottom:1px solid var(--site-line); }
.report-list .report-list-link { min-width:0; flex:1; display:grid;
  grid-template-columns:minmax(190px,1fr) minmax(150px,.8fr) auto;
  gap:1rem; align-items:center; padding:1rem .2rem; color:inherit; text-decoration:none; }
.report-list li:hover { background:var(--site-panel); }
.report-list strong { color:var(--site-navy); font:700 1.06rem/1.3 Georgia,"Times New Roman",serif; }
.report-list span { color:var(--site-muted); font-size:.9rem; }
.site-badge { display:inline-block; justify-self:end; padding:.18rem .5rem; border-radius:999px;
  color:#31536b !important; background:#e7f0f5; font-size:.72rem !important; font-weight:800; text-transform:uppercase; }
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
        "Payers",
        (
            (
                "payer-strategy",
                "Payer Strategy",
                (
                    r"\bpayers?\b",
                    r"\binsurers?\b",
                    r"\bhealth plans?\b",
                    r"\bhumana\b",
                    r"\bunitedhealth\b",
                    r"\baetna\b",
                    r"\bcentene\b",
                    r"\bcigna\b",
                    r"\belevance\b",
                    r"\bmolina\b",
                    r"\boscar health\b",
                ),
            ),
            (
                "payment-integrity",
                "Payment Integrity",
                (
                    r"\bpayment integrity\b",
                    r"\bimproper payments?\b",
                    r"\bfraud\b",
                    r"\bclaims?\b",
                    r"\bcoding\b",
                    r"\bdenials?\b",
                    r"\bappeals?\b",
                    r"\bprior[- ]authorization\b",
                    r"\butilization management\b",
                ),
            ),
            (
                "risk-adjustment",
                "Risk",
                (
                    r"\brisk adjustment\b",
                    r"\brisk scores?\b",
                    r"\bradv\b",
                    r"\bhccs?\b",
                    r"\bcoding intensity\b",
                    r"\bmedical cost trends?\b",
                    r"\bactuarial\b",
                ),
            ),
            (
                "quality",
                "Quality",
                (
                    r"\bquality\b",
                    r"\bhedis\b",
                    r"\bstar ratings?\b",
                    r"\bcare gaps?\b",
                    r"\bpatient outcomes?\b",
                ),
            ),
        ),
    ),
    (
        "Providers",
        (
            (
                "provider-strategy",
                "Provider Strategy",
                (
                    r"\bproviders?\b",
                    r"\bhealth systems?\b",
                    r"\bhospitals?\b",
                    r"\bambulatory\b",
                    r"\bservice[- ]lines?\b",
                ),
            ),
            (
                "revenue-cycle-management",
                "Revenue Cycle Management",
                (
                    r"\brevenue[- ]cycle\b",
                    r"\breimbursement\b",
                    r"\bunderpayments?\b",
                    r"\bbilling\b",
                    r"\bcollections?\b",
                    r"\bno surprises act\b",
                    r"\bqualifying payment amount\b",
                    r"\bqpa\b",
                    r"\bcontract(?:ed)? rates?\b",
                ),
            ),
            (
                "imaging",
                "Imaging",
                (
                    r"\bimaging\b",
                    r"\bradiology\b",
                    r"\bdiagnostic images?\b",
                    r"\bpacs\b",
                    r"\b(?:ct|mri|pet) scans?\b",
                ),
            ),
            (
                "edi-interoperability",
                "EDI & Interoperability",
                (
                    r"\bedi\b",
                    r"\binteroperability\b",
                    r"\bdata exchange\b",
                    r"\bimage exchange\b",
                    r"\bcare everywhere\b",
                    r"\btefca\b",
                    r"\bclearinghouses?\b",
                ),
            ),
            (
                "clinical-decision-support",
                "Clinical Decision Support",
                (
                    r"\bclinical decision support\b",
                    r"\bclinical workflows?\b",
                    r"\bclinical evidence\b",
                    r"\bdecision accuracy\b",
                    r"\bdiagnostic support\b",
                ),
            ),
        ),
    ),
    (
        "Across the Business",
        (
            ("life-sciences", "Life Sciences", ()),
            (
                "policy-cross-sector",
                "Policy & Cross-Sector",
                (
                    r"\bpolicy\b",
                    r"\bregulation\b",
                    r"\bregulatory\b",
                    r"\bcms\b",
                    r"\bfda\b",
                    r"\bmedicaid\b",
                    r"\bmedicare\b",
                    r"\bcourt\b",
                    r"\bruling\b",
                    r"\badministration\b",
                    r"\benforcement\b",
                    r"\bfederal\b",
                ),
            ),
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
    profiles = config.settings.get("report_profiles", {})
    candidates: list[tuple[Path, ProjectConfig, str]] = []
    for folder in final_root.iterdir():
        if not folder.is_dir():
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder.name):
            candidates.append((folder, config.for_scope("healthcare"), folder.name))
        elif folder.name in profiles:
            scoped = config.for_scope(folder.name)
            for report_folder in folder.iterdir():
                if report_folder.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_folder.name):
                    candidates.append((report_folder, scoped, f"{folder.name}/{report_folder.name}"))
    for folder, scoped, archive_path in candidates:
        try:
            published = date.fromisoformat(folder.name)
        except ValueError:
            continue
        source = folder / report_html_name(published, scoped)
        manifest = read_json(folder / "manifest.json", {})
        if not source.is_file() or not isinstance(manifest, dict):
            continue
        report_type = str(manifest.get("report_type") or scoped.scope)
        reports.append(
            SiteReport(
                report_date=published,
                report_type=report_type,
                report_name=str(manifest.get("report_name") or scoped.report_name),
                market_data_as_of=str(manifest.get("market_data_as_of") or ""),
                quality=str(manifest.get("quality") or "unknown"),
                source=source,
                archive_path=archive_path,
            )
        )
    return sorted(
        reports,
        key=lambda item: (item.report_date, item.report_type == "healthcare"),
        reverse=True,
    )


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
        f'<a class="public-site-brand" href="{home}">Weekly Intelligence</a>'
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
        f"<title>{html.escape(title)} · Healthcare Intel Digest</title>"
        f"<style>{SITE_CSS}</style></head>"
        f'<body class="public-page-body">{_site_header(prefix, active)}'
        f'<main class="public-page">{body}'
        '<footer class="public-site-footer">Healthcare Intel Digest uses public market and '
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
        ("healthcare", "Healthcare Intel Report"),
        ("life-science-device", "Life Sciences Intel Report"),
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
            rows.append(
                f'<li class="report-list-item"><a class="report-list-link" href="{report.archive_path}/">'
                f"<strong>{_long_date(report.report_date)}</strong>"
                f"<span>Market data through {html.escape(market_date or 'not recorded')}</span>"
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
    if headline.report.report_type == "life-science-device":
        matches.append("life-sciences")
    for _group_label, topics in TOPIC_GROUPS:
        for slug, _topic_label, patterns in topics:
            if slug in {"life-sciences", "other"}:
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
    indexed = [(report, *_indexed_report_content(report)) for report in reports]
    dates = sorted({report.report_date for report in reports}, reverse=True)
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
                f"<h4>In the News</h4>{_index_link_list(headlines)}"
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
        if reports:
            latest = next(
                (report for report in reports if report.report_type == "healthcare"), reports[0]
            )
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
            _publish_report_downloads(reports, temporary, destination if destination.is_dir() else None)
        else:
            (temporary / "index.html").write_text(_empty_home(config), encoding="utf-8")
        atomic_replace_directory(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "status": "ok",
        "output": str(destination),
        "reports": len(reports),
        "latest_report": reports[0].report_date.isoformat() if reports else None,
    }
