from __future__ import annotations

import base64
import html
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

import markdown
from bs4 import BeautifulSoup

from .analysis import Baseline, format_percent, months_before
from .config import ProjectConfig
from .earnings import google_url

CSS = """
:root { color-scheme:light; --navy:#2c3331; --navy-2:#5a6360; --ink:#1e2422;
  --muted:#5a6360; --line:#d4cfc4; --panel:#e7e4dc; --paper:#fffdf8; --accent:#b33c28; }
@import url("https://fonts.googleapis.com/css2?family=Source+Sans+3:ital,wght@0,400;0,600;0,700;1,400&family=Zilla+Slab:wght@600;700&display=swap");
* { box-sizing:border-box; }
html { scroll-behavior:smooth; scroll-padding-top:1.25rem; }
body { margin:0; color:var(--ink); background:#f6f3ec;
  font:16px/1.58 "Source Sans 3",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.page-shell { width:min(1500px,100%); margin:0 auto; padding:1.5rem;
  display:grid; grid-template-columns:235px minmax(0,1120px); gap:2rem; align-items:start; }
.report-nav { position:sticky; top:1.5rem; max-height:calc(100vh - 3rem); overflow:auto;
  border-top:5px solid var(--navy); background:var(--paper); box-shadow:0 5px 20px #18324814;
  padding:1rem 1rem 1.1rem; font-size:.87rem; }
.report-nav-title { margin:0 0 .65rem; color:var(--navy); font:700 1.05rem/1.25 "Zilla Slab",Georgia,serif; }
.report-nav ul { margin:0; padding:0; list-style:none; }
.report-nav li { margin:.25rem 0; }
.report-nav li ul { border-left:2px solid #dce6ed; margin:.35rem 0 .55rem .25rem; padding-left:.7rem; }
.report-nav a { color:#405466; text-decoration:none; }
.report-nav a:hover { color:var(--navy-2); text-decoration:underline; }
main { min-width:0; background:var(--paper); border-top:7px solid var(--navy);
  box-shadow:0 8px 30px #18324817; padding:3rem 3.5rem 5rem; }
h1,h2,h3,h4 { color:var(--ink); font-family:"Zilla Slab",Georgia,serif; line-height:1.2; }
h1 { margin:0; font-size:2.55rem; letter-spacing:-.025em; }
h2 { margin-top:2.25em; padding-bottom:.35rem; border-bottom:3px solid var(--navy); font-size:1.75rem; }
h3 { margin-top:1.8em; font-size:1.32rem; }
h4 { font-size:1.08rem; }
a { color:#b33c28; text-underline-offset:2px; }
.report-meta { margin:1rem 0 1.35rem; padding:.85rem 1rem; background:var(--panel);
  border-left:4px solid var(--navy-2); color:#40505e; }
.report-meta span { display:block; }
.section-jump-list { columns:2; padding:1rem 1.25rem 1rem 2.25rem; background:var(--panel); border-radius:4px; }
.strategy-narrative-links { margin:.8rem 0 1.8rem; padding:1rem 1.25rem; background:var(--panel); border-radius:4px; }
.strategy-narrative-links ul { margin:0; padding-left:1.25rem; }
.strategy-narrative-links li { margin:.3rem 0; }
.return-badge { display:inline-block; margin-left:.35rem; padding:.13rem .48rem; border-radius:999px;
  font:700 .78rem/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; vertical-align:.12em; }
.category-return { font-size:.76rem; }
.table-wrap { overflow-x:auto; margin:1rem 0 1.7rem; border:1px solid var(--line); border-radius:5px; }
table { border-collapse:collapse; width:100%; margin:0; font-size:.9rem; font-variant-numeric:tabular-nums; }
th,td { border-bottom:1px solid var(--line); padding:.53rem .62rem; text-align:right; vertical-align:top; white-space:nowrap; }
th:first-child,td:first-child { text-align:left; }
th { background:#2c3331; color:#fffdf8; position:sticky; top:0; z-index:1; font-weight:700; }
th.sortable-heading { cursor:pointer; user-select:none; }
th.sortable-heading:hover { background:#3a423e; }
th.sortable-heading::after { content:" ↕"; color:#718696; font-size:.78em; }
th.sort-asc::after { content:" ↑"; color:var(--navy); }
th.sort-desc::after { content:" ↓"; color:var(--navy); }
tbody tr:hover td { box-shadow:inset 0 0 0 999px #ffffff26; }
tbody tr:last-child td { border-bottom:0; }
td.text { text-align:left; }
td.missing { color:var(--muted); }
blockquote { border-left:4px solid var(--accent); margin-left:0; padding:.65rem 1rem; background:#f6f3ec; }
code { background:var(--panel); padding:.1rem .25rem; }
img { display:block; max-width:100%; height:auto; margin:1rem auto 1.7rem; }
.metadata { color:var(--muted); margin-top:-.6rem; }
.good {color:#3f5c4a}.bad {color:#8c2e1e}
.rank-change-up { color:#3f5c4a; font-weight:800; }
.rank-change-down { color:#8c2e1e; font-weight:800; }
@media (max-width:1050px) {
  .page-shell { display:block; padding:0; }
  .report-nav { position:relative; top:0; max-height:none; border-top:0; border-bottom:4px solid var(--navy);
    box-shadow:none; padding:.75rem 1rem; }
  .report-nav ul { display:flex; flex-wrap:wrap; gap:.15rem 1rem; }
  .report-nav li ul { display:none; }
  main { box-shadow:none; border-top:0; }
}
@media (max-width:700px) {
  main { padding:2rem 1rem 4rem; } h1{font-size:2rem} h2{font-size:1.45rem}
  table{font-size:.8rem} th,td{padding:.44rem .5rem} .section-jump-list{columns:1}
}
@media print { body{background:#fff}.page-shell{display:block;padding:0}.report-nav{display:none}main{box-shadow:none;border:0;padding:0} }
"""

SORT_SCRIPT = """
document.querySelectorAll('table.sortable').forEach((table) => {
  table.querySelectorAll('th[data-column]').forEach((heading) => {
    heading.addEventListener('click', () => {
      const index = Number(heading.dataset.column);
      const numeric = heading.dataset.type === 'number';
      const descending = heading.classList.contains('sort-asc');
      table.querySelectorAll('th').forEach((item) => item.classList.remove('sort-asc','sort-desc'));
      heading.classList.add(descending ? 'sort-desc' : 'sort-asc');
      const rows = Array.from(table.tBodies[0].rows);
      rows.sort((left, right) => {
        const a = left.cells[index].dataset.sort || '';
        const b = right.cells[index].dataset.sort || '';
        const result = numeric ? ((Number(a) || 0) - (Number(b) || 0)) : a.localeCompare(b);
        return descending ? -result : result;
      });
      rows.forEach((row) => table.tBodies[0].appendChild(row));
    });
  });
});
"""

POSITIVE_COLORS = ("#d6ecd4", "#a9d9a4", "#7cc077", "#2f9e44", "#1a7a3c")
NEGATIVE_COLORS = ("#fbd5d4", "#f5aead", "#ee8483", "#e34948", "#c0302f")
NEUTRAL_COLOR = "#f0efec"


@cache
def _plotting() -> tuple[Any, Any]:
    def writable_directory(path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".ethanol-write-check-", dir=path):
                pass
            return True
        except OSError:
            return False

    if "MPLCONFIGDIR" not in os.environ:
        default_config = Path.home() / ".matplotlib"
        if not writable_directory(default_config):
            fallback = Path(tempfile.gettempdir()) / "ethanol-report-matplotlib"
            fallback.mkdir(parents=True, exist_ok=True)
            os.environ["MPLCONFIGDIR"] = str(fallback)
    if "XDG_CACHE_HOME" not in os.environ:
        default_cache = Path.home() / ".cache"
        if not writable_directory(default_cache):
            fallback_cache = Path(tempfile.gettempdir()) / "ethanol-report-cache"
            fallback_cache.mkdir(parents=True, exist_ok=True)
            os.environ["XDG_CACHE_HOME"] = str(fallback_cache)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    return mdates, plt


@dataclass(frozen=True)
class HtmlCell:
    content: str
    sort_value: str | float | int | None = None
    css_class: str = ""
    style: str = ""


def _long_date(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _narrative_created(narrative: dict[str, Any] | None) -> str | None:
    if not narrative:
        return None
    fetched = str(narrative.get("fetched_at") or "")
    try:
        return _long_date(datetime.fromisoformat(fetched.replace("Z", "+00:00")).date())
    except ValueError:
        return str(narrative.get("period") or "") or None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def _internal_link(label: str, anchor: str) -> str:
    return f'<a href="#{html.escape(anchor, quote=True)}">{html.escape(label)}</a>'


def _contrast_text(background: str) -> str:
    values = [int(background[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values
    ]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return "#ffffff" if (1.05 / (luminance + 0.05)) >= ((luminance + 0.05) / 0.05) else "#111820"


def _return_background(value: float | None, maximum: float) -> tuple[str, str]:
    if value is None or math.isclose(value, 0.0, abs_tol=1e-15) or maximum <= 0:
        return NEUTRAL_COLOR, "#111820"
    ratio = min(abs(value) / maximum, 1.0)
    index = min(4, max(0, math.ceil(ratio * 5) - 1))
    background = (POSITIVE_COLORS if value > 0 else NEGATIVE_COLORS)[index]
    return background, _contrast_text(background)


def _return_cells(values: list[float | None], *, badge: bool = False) -> list[HtmlCell]:
    maximum = max((abs(value) for value in values if value is not None), default=0.0)
    output: list[HtmlCell] = []
    for value in values:
        background, foreground = _return_background(value, maximum)
        classes = "return-badge" if badge else ("missing" if value is None else "")
        output.append(
            HtmlCell(
                format_percent(value) if value is not None else "—",
                value,
                classes,
                f"background:{background};color:{foreground};",
            )
        )
    return output


def sortable_table(
    headers: list[str],
    rows: list[list[HtmlCell | Any]],
    *,
    numeric_columns: set[int] | None = None,
    text_columns: set[int] | None = None,
) -> str:
    if not rows:
        return "*No data available.*\n"
    numeric_columns = numeric_columns or set()
    text_columns = text_columns or {0}
    heading_html = "".join(
        f'<th class="sortable-heading" data-column="{index}" data-type="'
        f'{"number" if index in numeric_columns else "text"}">{html.escape(label)}</th>'
        for index, label in enumerate(headers)
    )
    body_rows: list[str] = []
    for row in rows:
        cells: list[str] = []
        for index, value in enumerate(row):
            cell = value if isinstance(value, HtmlCell) else HtmlCell(html.escape(str(value)))
            sort_value = (
                cell.sort_value
                if cell.sort_value is not None
                else re.sub("<[^>]+>", "", cell.content)
            )
            css_class = " ".join(
                item for item in ("text" if index in text_columns else "", cell.css_class) if item
            )
            cells.append(
                f'<td class="{html.escape(css_class, quote=True)}" '
                f'data-sort="{html.escape(str(sort_value), quote=True)}" '
                f'style="{html.escape(cell.style, quote=True)}">{cell.content}</td>'
            )
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<div class="table-wrap"><table class="sortable"><thead><tr>'
        + heading_html
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>\n"
    )


def _strip_narrative_section(body: str, title: str) -> str:
    lines = body.splitlines()
    output: list[str] = []
    skipping = False
    level = 0
    target = title.casefold()
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match and not skipping and match.group(2).strip().casefold() == target:
            skipping = True
            level = len(match.group(1))
            continue
        if skipping:
            if match and len(match.group(1)) <= level:
                skipping = False
            else:
                continue
        if not skipping:
            output.append(line)
    return "\n".join(output)


def _presentation_narrative(body: str) -> str:
    body = re.sub(
        r"^\s*\*{0,2}(?:Strategy brief for\s+)?Week of\s+.+?\*{0,2}\s*$",
        "",
        body,
        count=1,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    body = _strip_narrative_section(body, "Functional strategy summary")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return _add_strategy_narrative_links(body)


def _add_strategy_narrative_links(body: str) -> str:
    lines = body.splitlines()
    headings: list[tuple[int, int, str, str]] = []
    for index, line in enumerate(lines):
        markdown_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        html_match = re.match(r"^<h([1-6])(?:\s[^>]*)?>(.*?)</h\1>\s*$", line)
        if markdown_match:
            headings.append((index, len(markdown_match.group(1)), markdown_match.group(2).strip(), "markdown"))
        elif html_match:
            label = BeautifulSoup(html_match.group(2), "html.parser").get_text(" ", strip=True)
            headings.append((index, int(html_match.group(1)), label, "html"))
    if not headings:
        return body

    section_level = min(level for _index, level, _label, _format in headings)
    numbered_links: list[tuple[str, str]] = []
    current_section_slug = "executive"
    for index, level, raw_label, heading_format in headings:
        label = _clean_strategy_headline(raw_label)
        is_numbered = bool(re.match(r"^\d+\.\s", label))
        if level == section_level and not is_numbered:
            anchor = _slug(label)
            current_section_slug = "executive" if anchor == "executive-readout" else anchor
        else:
            anchor = f"strategy-{current_section_slug}-{_slug(label)}"
        if is_numbered:
            numbered_links.append((label, anchor))
        if heading_format == "markdown":
            lines[index] = f'<h{level} id="{anchor}">{html.escape(label)}</h{level}>'
        else:
            lines[index] = f'<h{level} id="{anchor}">{html.escape(label)}</h{level}>'

    if not numbered_links:
        return "\n".join(lines)
    jump_list = [
        '<nav class="strategy-narrative-links" aria-label="Strategy narrative sections">',
        "<ul>",
    ]
    jump_list.extend(
        f'<li><a href="#{html.escape(anchor, quote=True)}">{html.escape(label)}</a></li>'
        for label, anchor in numbered_links
    )
    jump_list.extend(["</ul>", "</nav>", ""])
    return "\n".join([*jump_list, *lines])


def _clean_strategy_headline(label: str) -> str:
    label = re.sub(r"[*_`]+", "", label).strip()
    return re.sub(
        r"^(\d+\.\s+)(?:[A-Z][A-Z0-9]*(?:\s*/\s*[A-Z][A-Z0-9]*)*)\s+[—–-]\s+",
        r"\1",
        label,
    )


def format_cap(value: float | None) -> str:
    if value is None:
        return "n/a"
    for divisor, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= divisor:
            return f"${value / divisor:.1f}{suffix}"
    return f"${value:,.0f}"


def select_chart_tickers(snapshot: list[dict[str, Any]], config: ProjectConfig) -> list[str]:
    per_horizon = int(config.settings["report"].get("chart_stocks_per_horizon", 3))
    selected: list[str] = []
    seen: set[str] = set()
    for horizon in config.settings["report"]["return_horizons_months"]:
        rows: dict[str, dict[str, Any]] = {}
        for row in snapshot:
            if row["entity_type"] == "stock" and row["horizon_months"] == int(horizon):
                rows.setdefault(row["ticker"], row)
        ranked = sorted(
            (row for row in rows.values() if row["price_return"] is not None),
            key=lambda row: (-row["price_return"], row["ticker"]),
        )[:per_horizon]
        for row in ranked:
            if row["ticker"] not in seen:
                seen.add(row["ticker"])
                selected.append(row["ticker"])
    return selected


def render_charts(
    folder: Path,
    config: ProjectConfig,
    report_date: date,
    bars: dict[str, list[dict[str, Any]]],
    tickers: list[str],
) -> list[tuple[int, Path]]:
    mdates, plt = _plotting()
    assets = folder / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    benchmark = str(config.settings["report"].get("benchmark", "SPY"))
    charts: list[tuple[int, Path]] = []
    stock_colors = (
        "#1f77b4",
        "#d55e00",
        "#009e73",
        "#cc79a7",
        "#56b4e9",
        "#e69f00",
        "#0072b2",
        "#7a5195",
    )
    line_styles = ("-", "--", "-.", ":")
    stock_style = {
        ticker: (
            stock_colors[index % len(stock_colors)],
            line_styles[index // len(stock_colors) % len(line_styles)],
        )
        for index, ticker in enumerate(tickers)
    }
    for horizon in config.settings["report"]["chart_horizons_months"]:
        start = months_before(report_date, int(horizon))
        series: dict[str, tuple[list[date], list[float]]] = {}
        for ticker in [benchmark, *tickers]:
            eligible = [bar for bar in bars.get(ticker, []) if start <= bar["date"] <= report_date]
            if not eligible:
                continue
            eligible.sort(key=lambda item: item["date"])
            base = float(eligible[0]["close"])
            series[ticker] = (
                [bar["date"] for bar in eligible],
                [float(bar["close"]) / base * 100 for bar in eligible],
            )
        if not series:
            continue
        figure, axis = plt.subplots(figsize=(11.5, 5.5))
        plotted: list[tuple[str, list[date], list[float], str]] = []
        for ticker, (dates, values) in series.items():
            color, linestyle = (
                ("#59636c", "--")
                if ticker == benchmark
                else stock_style.get(ticker, ("#1f77b4", "-"))
            )
            axis.plot(
                mdates.date2num(dates),
                values,
                linewidth=2.3 if ticker == benchmark else 1.9,
                linestyle=linestyle,
                color=color,
            )
            plotted.append((ticker, dates, values, color))
        axis.axhline(100, color="#aeb7bf", linewidth=1, linestyle=":")
        axis.set_title(f"Last {horizon} months — indexed to 100")
        axis.set_ylabel("Indexed price")
        axis.grid(axis="y", alpha=0.18)
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        xmin, xmax = axis.get_xlim()
        label_x = xmax + (xmax - xmin) * 0.025
        axis.set_xlim(xmin, xmax + (xmax - xmin) * 0.19)
        ymin, ymax = axis.get_ylim()
        spacing = max((ymax - ymin) * 0.045, 2.0)
        label_positions: dict[str, float] = {}
        previous = -math.inf
        for ticker, _dates, values, _color in sorted(plotted, key=lambda item: item[2][-1]):
            position = max(values[-1], previous + spacing)
            label_positions[ticker] = position
            previous = position
        if label_positions and max(label_positions.values()) > ymax:
            axis.set_ylim(ymin, max(label_positions.values()) + spacing)
        for ticker, dates, values, color in plotted:
            end_x = mdates.date2num(dates[-1])
            label_y = label_positions[ticker]
            axis.plot(
                [end_x, label_x], [values[-1], label_y], color=color, linewidth=0.75, alpha=0.7
            )
            stock_return = values[-1] / 100 - 1
            axis.text(
                label_x,
                label_y,
                f"{ticker} {stock_return:+.1%}",
                color=color,
                fontsize=8 if len(plotted) > 7 else 9,
                fontweight="bold",
                va="center",
                ha="left",
            )
        figure.autofmt_xdate(rotation=0)
        figure.tight_layout()
        path = assets / f"performance-{horizon}m.webp"
        figure.savefig(
            path,
            dpi=150,
            bbox_inches="tight",
            format="webp",
            pil_kwargs={"lossless": True, "method": 6},
        )
        plt.close(figure)
        charts.append((int(horizon), path))
    return charts


def render_rank_comparison_chart(
    folder: Path, summary: dict[str, Any]
) -> Path | None:
    """Render the previous/current top-three rank comparison used in Notable Changes."""
    _mdates, plt = _plotting()
    groups = (
        ("Stocks", summary.get("stocks", {}).get("top", []), "ticker"),
        ("Sectors", summary.get("categories", {}).get("top", []), "category"),
    )
    if not any(rows for _title, rows, _field in groups):
        return None
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.2), squeeze=False)
    axes_list = list(axes[0])
    for axis, (title, rows, label_field) in zip(axes_list, groups, strict=True):
        rows = list(rows)
        if not rows:
            axis.axis("off")
            axis.set_title(title)
            continue
        labels = [
            str(row.get(label_field) or row.get("name", ""))
            for row in rows
        ][::-1]
        previous = [int(row["previous_rank"]) for row in rows][::-1]
        current = [int(row["current_rank"]) for row in rows][::-1]
        positions = list(range(len(rows)))
        for position, old_rank, new_rank in zip(positions, previous, current, strict=True):
            color = "#167344" if new_rank < old_rank else "#b42318" if new_rank > old_rank else "#64717d"
            axis.plot([old_rank, new_rank], [position, position], color=color, linewidth=2.4)
            axis.scatter([old_rank, new_rank], [position, position], color=["#8ca0ad", color], s=42, zorder=3)
        axis.set_yticks(positions, labels)
        axis.set_xlabel("Rank (1 = best)")
        axis.set_title(f"Top {int(summary.get('top_n', 3))} {title.lower()}")
        axis.set_xlim(max(previous + current) + 0.7, 0.5)
        axis.set_xticks(range(1, max(previous + current) + 1))
        axis.grid(axis="x", alpha=0.18)
        axis.spines[["top", "right", "left"]].set_visible(False)
    figure.suptitle("Previous report → current report", fontsize=14, fontweight="bold")
    figure.tight_layout()
    assets = folder / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    path = assets / "rank-comparison.webp"
    figure.savefig(
        path,
        dpi=150,
        bbox_inches="tight",
        format="webp",
        pil_kwargs={"lossless": True, "method": 6},
    )
    plt.close(figure)
    return path


def render_earnings_charts(
    folder: Path,
    config: ProjectConfig,
    report_date: date,
    bars: dict[str, list[dict[str, Any]]],
    tickers: list[str],
) -> dict[str, Path]:
    mdates, plt = _plotting()
    assets = folder / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    benchmark = str(config.settings["report"].get("benchmark", "SPY"))
    start = months_before(report_date, 3)
    membership: dict[str, str] = {}
    for category, members in config.universe.categories.items():
        for company in members:
            membership.setdefault(company.ticker, category)
    charts: dict[str, Path] = {}
    for featured in tickers:
        featured_category = membership.get(featured)
        if not featured_category:
            continue
        peers = [company.ticker for company in config.universe.categories[featured_category]]
        ordered_tickers = [*peers, benchmark]
        series: dict[str, tuple[list[date], list[float]]] = {}
        for ticker in ordered_tickers:
            eligible = [bar for bar in bars.get(ticker, []) if start <= bar["date"] <= report_date]
            if not eligible:
                continue
            eligible.sort(key=lambda item: item["date"])
            base = float(eligible[0]["close"])
            series[ticker] = (
                [bar["date"] for bar in eligible],
                [float(bar["close"]) / base * 100 for bar in eligible],
            )
        if featured not in series or benchmark not in series:
            continue

        figure, axis = plt.subplots(figsize=(11.5, 5.5))
        plotted: list[tuple[str, list[date], list[float], str, float]] = []
        for ticker in ordered_tickers:
            if ticker not in series:
                continue
            dates, values = series[ticker]
            if ticker == featured:
                color, linewidth, linestyle, zorder = "#2c3331", 3.4, "-", 4
            elif ticker == benchmark:
                color, linewidth, linestyle, zorder = "#3f4b55", 2.3, "--", 3
            else:
                color, linewidth, linestyle, zorder = "#aab5be", 1.25, "-", 1
            axis.plot(
                mdates.date2num(dates),
                values,
                color=color,
                linewidth=linewidth,
                linestyle=linestyle,
                alpha=0.9 if ticker in {featured, benchmark} else 0.68,
                zorder=zorder,
            )
            plotted.append((ticker, dates, values, color, linewidth))

        axis.axhline(100, color="#c5cdd3", linewidth=1, linestyle=":")
        axis.set_title(f"{featured} vs. {featured_category} peers and S&P 500 — last 3 months")
        axis.set_ylabel("Indexed price (start = 100)")
        axis.grid(axis="y", alpha=0.18)
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        xmin, xmax = axis.get_xlim()
        label_x = xmax + (xmax - xmin) * 0.025
        axis.set_xlim(xmin, xmax + (xmax - xmin) * 0.18)
        ymin, ymax = axis.get_ylim()
        spacing = max((ymax - ymin) * 0.04, 1.35)
        label_positions: dict[str, float] = {}
        previous = -math.inf
        for ticker, _dates, values, _color, _linewidth in sorted(
            plotted, key=lambda item: item[2][-1]
        ):
            position = max(values[-1], previous + spacing)
            label_positions[ticker] = position
            previous = position
        if label_positions and max(label_positions.values()) > ymax:
            axis.set_ylim(ymin, max(label_positions.values()) + spacing)
        for ticker, dates, values, color, _linewidth in plotted:
            label = "S&P 500 (SPY)" if ticker == "SPY" else ticker
            label_y = label_positions[ticker]
            end_x = mdates.date2num(dates[-1])
            axis.plot(
                [end_x, label_x],
                [values[-1], label_y],
                color=color,
                linewidth=0.8,
                alpha=0.7,
            )
            axis.text(
                label_x,
                label_y,
                f"{label} {values[-1] / 100 - 1:+.1%}",
                color=color,
                fontsize=8,
                fontweight="bold" if ticker in {featured, benchmark} else "normal",
                va="center",
                ha="left",
            )
        figure.autofmt_xdate(rotation=0)
        figure.tight_layout()
        path = assets / f"earnings-{_slug(featured)}-3m.webp"
        figure.savefig(
            path,
            dpi=150,
            bbox_inches="tight",
            format="webp",
            pil_kwargs={"lossless": True, "method": 6},
        )
        plt.close(figure)
        charts[featured] = path
    return charts


def _stock_facts(snapshot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for row in snapshot:
        if row["entity_type"] != "stock":
            continue
        ticker = str(row["ticker"])
        item = facts.setdefault(
            ticker,
            {
                "name": row["name"],
                "market_cap": row.get("market_cap"),
                "categories": [],
                "returns": {},
            },
        )
        if row["category"] not in item["categories"]:
            item["categories"].append(row["category"])
        item["returns"][int(row["horizon_months"])] = row.get("price_return")
    return facts


def _company_cell(name: str, ticker: str, earnings_tickers: set[str]) -> HtmlCell:
    content = (
        _internal_link(name, f"earnings-{_slug(ticker)}")
        if ticker in earnings_tickers
        else html.escape(name)
    )
    return HtmlCell(content, name.casefold())


def _ticker_cell(ticker: str, overview_tickers: set[str]) -> HtmlCell:
    content = (
        _internal_link(ticker, f"company-{_slug(ticker)}")
        if ticker in overview_tickers
        else html.escape(ticker)
    )
    return HtmlCell(content, ticker.casefold(), "text")


def _rank_change_table(
    rows: list[dict[str, Any]],
    *,
    stocks: bool,
    earnings_tickers: set[str],
    overview_tickers: set[str],
) -> str:
    table_rows: list[list[HtmlCell]] = []
    rows = sorted(rows, key=lambda row: (int(row["current_rank"]), row["name"]))
    return_cells = _return_cells([row.get("current_return") for row in rows])
    for index, row in enumerate(rows):
        if stocks:
            name = _company_cell(row["name"], row["ticker"], earnings_tickers)
            ticker = _ticker_cell(row["ticker"], overview_tickers)
            entity = HtmlCell(f"{name.content} ({ticker.content})", row["name"].casefold())
        else:
            entity = HtmlCell(
                _internal_link(row["name"], f"category-{_slug(row['name'])}"),
                row["name"].casefold(),
            )
        delta = int(row["rank_delta"])
        direction = "↑" if delta > 0 else "↓" if delta < 0 else "—"
        change_class = "rank-change-up" if delta > 0 else "rank-change-down" if delta < 0 else ""
        table_rows.append(
            [
                entity,
                HtmlCell(f"#{int(row['previous_rank'])}", int(row["previous_rank"])),
                HtmlCell(f"#{int(row['current_rank'])}", int(row["current_rank"])),
                HtmlCell(f"{direction} {abs(delta)}", -delta, change_class),
                return_cells[index],
            ]
        )
    return sortable_table(
        ["Entity", "Previous", "Current", "Change", "Current return"],
        table_rows,
        numeric_columns={1, 2, 3, 4},
        text_columns={0},
    )


def _summary_text(value: Any) -> str:
    return re.sub(
        r"\b(?:summarize_auto|insights_auto|expand_more|search_spark)\b\s*",
        "",
        str(value or ""),
    ).strip()


def build_markdown(context: dict[str, Any]) -> str:
    config: ProjectConfig = context["config"]
    report_date: date = context["report_date"]
    snapshot: list[dict[str, Any]] = context["snapshot"]
    notable: list[dict[str, Any]] = context["notable"]
    notable_summary: dict[str, Any] = context.get("notable_summary", {})
    horizons = [int(item) for item in config.settings["report"]["return_horizons_months"]]
    facts = _stock_facts(snapshot)
    recent = context["recent_earnings"]
    summaries = sorted(
        (
            item
            for item in recent
            if item.get("summary") or item.get("at_a_glance") or item.get("key_moments")
        ),
        key=lambda item: (
            -(facts.get(item["ticker"], {}).get("market_cap") or 0),
            item["ticker"],
        ),
    )
    earnings_tickers = {item["ticker"] for item in summaries}
    overview_tickers = set(config.universe.companies)
    narrative = context.get("narrative")
    narrative_created = _narrative_created(narrative)

    metadata = [
        f"<strong>Week of {_long_date(report_date)}</strong>",
        f"Market data through: {_long_date(context['market_data_as_of'])}",
    ]
    if narrative_created:
        metadata.append(f"Narrative created: {html.escape(narrative_created)}")
    lines = [
        f"# {config.settings['report']['name']}",
        "",
        '<div class="report-meta">'
        + "".join(f"<span>{item}</span>" for item in metadata)
        + "</div>",
        "",
        str(config.settings["report"].get("description", "")),
        "",
        "## In the News",
        "",
    ]
    if narrative:
        lines.append(_presentation_narrative(str(narrative.get("body") or "")))
    else:
        lines.append("No strategy narrative is available.")

    lines.extend(["", "## Notable Changes", ""])
    baseline: Baseline | None = context.get("baseline")
    if baseline:
        lines.append(
            f"Comparison with the final report dated {_long_date(baseline.report_date)} "
            f"(market data through {_long_date(baseline.market_data_as_of)})."
        )
    if baseline and notable_summary:
        lines.extend(["", "### Sectors", "", "#### Top-three comparison", ""])
        lines.append(
            _rank_change_table(
                notable_summary.get("categories", {}).get("top", []),
                stocks=False,
                earnings_tickers=earnings_tickers,
                overview_tickers=overview_tickers,
            )
        )
        category_largest = notable_summary.get("categories", {}).get("largest", [])
        if category_largest:
            lines.extend(["", "#### Largest rank changes", ""])
            lines.append(
                _rank_change_table(
                    category_largest,
                    stocks=False,
                    earnings_tickers=earnings_tickers,
                    overview_tickers=overview_tickers,
                )
            )
        lines.extend(["", "### Stocks", "", "#### Top-three comparison", ""])
        lines.append(
            _rank_change_table(
                notable_summary.get("stocks", {}).get("top", []),
                stocks=True,
                earnings_tickers=earnings_tickers,
                overview_tickers=overview_tickers,
            )
        )
        lines.extend(["", "#### Largest rank changes", ""])
        lines.append(
            _rank_change_table(
                notable_summary.get("stocks", {}).get("largest", []),
                stocks=True,
                earnings_tickers=earnings_tickers,
                overview_tickers=overview_tickers,
            )
        )
    elif notable:
        for notable_row in notable:
            lines.append(f"- {notable_row['detail']}")
    moves = context["period_moves"]
    if moves["categories"]:
        rows = sorted(
            moves["categories"],
            key=lambda item: item["price_move"] if item["price_move"] is not None else -math.inf,
            reverse=True,
        )
        current_category_returns = {
            row["category"]: row.get("price_return")
            for row in snapshot
            if row["entity_type"] == "category" and row["horizon_months"] == 12
        }
        previous_category_returns = {
            row["category"]: row.get("price_return")
            for row in (baseline.snapshot if baseline else [])
            if row["entity_type"] == "category" and row["horizon_months"] == 12
        }
        return_cells = _return_cells([row["price_move"] for row in rows])
        previous_cells = _return_cells(
            [previous_category_returns.get(row["category"]) for row in rows]
        )
        current_cells = _return_cells(
            [current_category_returns.get(row["category"]) for row in rows]
        )
        lines.extend(["", "### Subcategory movement since the previous report", ""])
        lines.append(
            sortable_table(
                [
                    "Subcategory",
                    "Move",
                    "Last Report, 12m Ret",
                    "Current Report, 12m Ret",
                ],
                [
                    [
                        HtmlCell(
                            _internal_link(
                                row["category"], f"category-{_slug(row['category'])}"
                            ),
                            row["category"].casefold(),
                        ),
                        return_cells[index],
                        previous_cells[index],
                        current_cells[index],
                    ]
                    for index, row in enumerate(rows)
                ],
                numeric_columns={1, 2, 3},
            )
        )
    if moves["stocks"]:
        shown = int(config.settings["notable_changes"].get("movers_shown", 3))
        eligible = [row for row in moves["stocks"] if row["price_move"] is not None]
        gainers = sorted(
            (row for row in eligible if row["price_move"] > 0), key=lambda row: -row["price_move"]
        )[:shown]
        decliners = sorted(
            (row for row in eligible if row["price_move"] < 0), key=lambda row: row["price_move"]
        )[:shown]
        rows = gainers + decliners
        return_cells = _return_cells([row["price_move"] for row in rows])
        lines.extend(["", "### Largest company moves", ""])
        lines.append(
            sortable_table(
                ["Direction", "Company", "Ticker", "Move"],
                [
                    [
                        HtmlCell(
                            "Gain" if row["price_move"] > 0 else "Decline",
                            "0" if row["price_move"] > 0 else "1",
                        ),
                        _company_cell(row["name"], row["ticker"], earnings_tickers),
                        _ticker_cell(row["ticker"], overview_tickers),
                        return_cells[index],
                    ]
                    for index, row in enumerate(rows)
                ],
                numeric_columns={3},
                text_columns={0, 1, 2},
            )
        )

    lines.extend(["", "## Subcategory Performance", ""])
    category_rows: list[list[HtmlCell]] = []
    category_values: dict[int, list[float | None]] = {horizon: [] for horizon in horizons}
    category_data: list[dict[str, Any]] = []
    for category, members in config.universe.categories.items():
        horizon_rows = {
            horizon: next(
                row
                for row in snapshot
                if row["entity_type"] == "category"
                and row["category"] == category
                and row["horizon_months"] == horizon
            )
            for horizon in horizons
        }
        item_returns: dict[int, float | None] = {
            horizon: horizon_rows[horizon].get("price_return") for horizon in horizons
        }
        item: dict[str, Any] = {
            "category": category,
            "companies": len(members),
            "market_cap": horizon_rows[horizons[0]].get("market_cap"),
            "returns": item_returns,
        }
        category_data.append(item)
        for horizon in horizons:
            category_values[horizon].append(item_returns[horizon])
    category_return_cells = {
        horizon: _return_cells(values) for horizon, values in category_values.items()
    }
    for index, item in enumerate(category_data):
        category_rows.append(
            [
                HtmlCell(
                    _internal_link(item["category"], f"category-{_slug(item['category'])}"),
                    item["category"].casefold(),
                ),
                HtmlCell(str(item["companies"]), item["companies"]),
                HtmlCell(format_cap(item["market_cap"]), item["market_cap"]),
                *[category_return_cells[horizon][index] for horizon in horizons],
            ]
        )
    lines.append(
        sortable_table(
            [
                "Subcategory",
                "Companies",
                "Market cap",
                *[f"{horizon}m Return" for horizon in horizons],
            ],
            category_rows,
            numeric_columns=set(range(1, 3 + len(horizons))),
        )
    )
    lines.append(
        "Subcategory returns use the most recently saved market capitalizations as weights."
    )

    lines.extend(["", "## Stock Performance vs. SPY", ""])
    lines.append(
        "The same selected stocks appear in every chart. Each line is labeled at the right with its ticker and return for the displayed window."
    )
    for horizon, path in context["charts"]:
        lines.extend(
            [
                f"### Last {horizon} months",
                "",
                f"![{horizon}-month indexed performance](assets/{path.name})",
                "",
            ]
        )

    lines.extend(["", "## Current Top Stocks", ""])
    top_count = int(config.settings["report"].get("top_stocks_shown", 5))
    for horizon in horizons:
        unique: dict[str, dict[str, Any]] = {}
        for item in snapshot:
            if item["entity_type"] == "stock" and item["horizon_months"] == horizon:
                unique.setdefault(item["ticker"], item)
        ranked = sorted(
            (row for row in unique.values() if row["overall_rank"] is not None),
            key=lambda row: (row["overall_rank"], row["ticker"]),
        )[:top_count]
        return_cells = _return_cells([row["price_return"] for row in ranked])
        lines.extend([f"### Last {horizon} months", ""])
        lines.append(
            sortable_table(
                ["Rank", "Company", "Ticker", "Market cap", "Return"],
                [
                    [
                        HtmlCell(str(row["overall_rank"]), row["overall_rank"]),
                        _company_cell(row["name"], row["ticker"], earnings_tickers),
                        _ticker_cell(row["ticker"], overview_tickers),
                        HtmlCell(format_cap(row["market_cap"]), row["market_cap"]),
                        return_cells[index],
                    ]
                    for index, row in enumerate(ranked)
                ],
                numeric_columns={0, 3, 4},
                text_columns={1, 2},
            )
        )

    lines.extend(["", "## Companies by Subcategory", ""])
    category_3m = [item["returns"].get(3) for item in category_data]
    category_badges = _return_cells(category_3m, badge=True)
    for category_index, (category, members) in enumerate(config.universe.categories.items()):
        badge = category_badges[category_index]
        heading = (
            f'<h3 id="category-{_slug(category)}">'
            f'<a href="#subcategory-performance">{html.escape(category)}</a>'
            f'<span class="{badge.css_class} category-return" style="{badge.style}">Last 3m: {html.escape(badge.content)}</span>'
            "</h3>"
        )
        lines.extend([heading, ""])
        rows_by_horizon: dict[int, list[float | None]] = {
            horizon: [facts[company.ticker]["returns"].get(horizon) for company in members]
            for horizon in horizons
        }
        category_member_return_cells = {
            horizon: _return_cells(values) for horizon, values in rows_by_horizon.items()
        }
        company_rows: list[list[HtmlCell]] = []
        for member_index, company in enumerate(members):
            fact = facts[company.ticker]
            company_rows.append(
                [
                    _company_cell(company.name, company.ticker, earnings_tickers),
                    _ticker_cell(company.ticker, overview_tickers),
                    HtmlCell(format_cap(fact["market_cap"]), fact["market_cap"]),
                    *[category_member_return_cells[horizon][member_index] for horizon in horizons],
                ]
            )
        lines.append(
            sortable_table(
                [
                    "Company",
                    "Ticker",
                    "Market cap",
                    *[f"{horizon}m Return" for horizon in horizons],
                ],
                company_rows,
                numeric_columns=set(range(2, 3 + len(horizons))),
                text_columns={0, 1},
            )
        )

    lines.extend(["", "## Upcoming Earnings", ""])
    upcoming = context["upcoming_earnings"]
    if not upcoming:
        lines.append("No saved earnings dates fall within the next seven days.")
    else:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in upcoming:
            categories = facts.get(row["ticker"], {}).get("categories", ["Uncategorized"])
            grouped.setdefault(categories[0], []).append(row)
        for category in config.universe.categories:
            category_rows_upcoming = grouped.get(category, [])
            if not category_rows_upcoming:
                continue
            category_rows_upcoming.sort(
                key=lambda row: -(facts[row["ticker"]].get("market_cap") or 0)
            )
            three_month = [facts[row["ticker"]]["returns"].get(3) for row in category_rows_upcoming]
            twelve_month = [
                facts[row["ticker"]]["returns"].get(12) for row in category_rows_upcoming
            ]
            three_cells = _return_cells(three_month)
            twelve_cells = _return_cells(twelve_month)
            lines.extend([f"### {category}", ""])
            lines.append(
                sortable_table(
                    ["Company", "Ticker", "Date", "Market cap", "3m Return", "12m Return"],
                    [
                        [
                            _company_cell(row["name"], row["ticker"], earnings_tickers),
                            _ticker_cell(row["ticker"], overview_tickers),
                            HtmlCell(_long_date(date.fromisoformat(row["date"])), row["date"]),
                            HtmlCell(
                                format_cap(facts[row["ticker"]]["market_cap"]),
                                facts[row["ticker"]]["market_cap"],
                            ),
                            three_cells[index],
                            twelve_cells[index],
                        ]
                        for index, row in enumerate(category_rows_upcoming)
                    ],
                    numeric_columns={3, 4, 5},
                    text_columns={0, 1, 2},
                )
            )

    lines.extend(["", "## Recent Earnings Highlights — 3m Ret", ""])
    if not summaries:
        lines.append("No earnings highlights fall within this report's window.")
    else:
        lines.append("Companies covered in this section:")
        lines.append('<ul class="section-jump-list">')
        for item in summaries:
            lines.append(
                f'<li><a href="#earnings-{_slug(item["ticker"])}">{html.escape(item["name"])} ({html.escape(item["ticker"])})</a></li>'
            )
        lines.append("</ul>")
    recent_returns = [facts.get(item["ticker"], {}).get("returns", {}).get(3) for item in summaries]
    recent_badges = _return_cells(recent_returns, badge=True)
    for index, item in enumerate(summaries):
        badge = recent_badges[index]
        ticker = str(item["ticker"])
        ticker_label = (
            _internal_link(ticker, f"company-{_slug(ticker)}")
            if ticker in overview_tickers
            else html.escape(ticker)
        )
        lines.extend(
            [
                f'<h3 id="earnings-{_slug(ticker)}">{html.escape(item["name"])} ({ticker_label}) '
                f'<span class="{badge.css_class}" style="{badge.style}">{html.escape(badge.content)}</span></h3>',
                "",
                f"**Reported:** {_long_date(date.fromisoformat(item['last_report_date']))} · "
                f"[Google Finance earnings page]({google_url(item['ticker'], context['reference'].get(item['ticker'], {}).get('exchange'))})",
                "",
            ]
        )
        chart_path = context.get("earnings_charts", {}).get(item["ticker"])
        if chart_path:
            lines.extend(
                [
                    f"![{html.escape(item['name'])} versus category peers and the S&P 500](assets/{chart_path.name})",
                    "",
                ]
            )
        summary = _summary_text(item.get("summary"))
        if summary:
            lines.extend(["#### Earnings Call Summary", "", summary, ""])
        glance = item.get("at_a_glance") or []
        if glance:
            lines.extend(["#### At a Glance", ""])
            for insight in glance:
                headline = _summary_text(insight.get("headline"))
                detail = _summary_text(insight.get("detail"))
                prefix = f"**{html.escape(headline)}:** " if headline else ""
                lines.append(f"- {prefix}{html.escape(detail)}")
            lines.append("")
        moments = item.get("key_moments", [])
        if moments:
            lines.extend(["#### Key Moments from the Call", ""])
            for moment in moments:
                lines.append(
                    f"- **{moment['timestamp']} — {_summary_text(moment['title'])}:** {_summary_text(moment['blurb'])}"
                )
        if not summary and not glance and not moments:
            lines.append(
                "No transcript summary, at-a-glance insights, or key moments were available."
            )

    lines.extend(["", "## Company Overviews", ""])
    overview_charts: dict[str, Path] = context.get("overview_charts", {})
    for ticker, company in config.universe.companies.items():
        reference = context["reference"].get(ticker, {})
        fact = facts.get(ticker, {})
        returns = fact.get("returns", {})
        lines.extend(
            [
                f'<h3 id="company-{_slug(ticker)}">{html.escape(company.name)} ({html.escape(ticker)})</h3>',
                "",
                f"*{', '.join(fact.get('categories', [])) or 'Uncategorized'} · {format_cap(fact.get('market_cap'))} · "
                f"3m {format_percent(returns.get(3))} · 12m {format_percent(returns.get(12))} · 24m {format_percent(returns.get(24))}*",
                "",
                f"[Google Finance]({google_url(ticker, reference.get('exchange'))})",
                "",
                company.description,
                "",
            ]
        )
        chart_path = overview_charts.get(ticker)
        if chart_path:
            lines.extend(
                [
                    f"![{html.escape(company.name)} versus category peers and the S&P 500](assets/{chart_path.name})",
                    "",
                ]
            )
        if reference.get("description") and reference["description"] != company.description:
            lines.extend([str(reference["description"]), ""])

    lines.append("")
    return "\n".join(lines)


def _report_file_prefix(config: ProjectConfig | None) -> str:
    if config is None:
        return "Corn and Ethanol Intel"
    return config.report_name


def report_html_name(report_date: date, config: ProjectConfig | None = None) -> str:
    return f"{_report_file_prefix(config)}-{report_date.isoformat()}.html"


def _navigation(body: str) -> tuple[str, str]:
    soup = BeautifulSoup(body, "html.parser")
    headings = soup.find_all("h2")
    items: list[str] = []
    for heading in headings:
        anchor = str(heading.get("id") or _slug(heading.get_text(" ", strip=True)))
        heading["id"] = anchor
        label = heading.get_text(" ", strip=True)
        nested: list[str] = []
        if label.startswith("Recent Earnings Highlights") or label == "Company Overviews":
            sibling = heading.find_next_sibling()
            while sibling is not None and sibling.name != "h2":
                if sibling.name == "h3":
                    nested_anchor = str(
                        sibling.get("id") or _slug(sibling.get_text(" ", strip=True))
                    )
                    sibling["id"] = nested_anchor
                    nested_label = sibling.get_text(" ", strip=True)
                    nested.append(
                        f'<li><a href="#{html.escape(nested_anchor, quote=True)}">{html.escape(nested_label)}</a></li>'
                    )
                sibling = sibling.find_next_sibling()
        nested_html = "<ul>" + "".join(nested) + "</ul>" if nested else ""
        items.append(
            f'<li><a href="#{html.escape(anchor, quote=True)}">{html.escape(label)}</a>{nested_html}</li>'
        )
    navigation = (
        '<nav class="report-nav" aria-label="Report navigation">'
        '<p class="report-nav-title">In this report</p><ul>' + "".join(items) + "</ul></nav>"
    )
    return navigation, str(soup)


def _html_document(
    folder: Path,
    markdown_text: str,
    *,
    embed_images: bool,
) -> str:
    body = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        output_format="html5",
    )
    if embed_images:
        soup = BeautifulSoup(body, "html.parser")
        for image_node in soup.select('img[src^="assets/"]'):
            relative = Path(str(image_node.get("src") or ""))
            image_path = folder / relative
            if not image_path.is_file():
                raise RuntimeError(f"Cannot embed missing report image: {relative}")
            mime_type = "image/webp" if image_path.suffix.casefold() == ".webp" else "image/png"
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            image_node["src"] = f"data:{mime_type};base64,{encoded}"
        body = str(soup)
    title_match = re.search(r"^# (.+)$", markdown_text, re.M)
    title = html.escape(title_match.group(1) if title_match else "Corn and Ethanol Intel")
    navigation, body = _navigation(body)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>{CSS}</style></head><body>"
        f'<div class="page-shell">{navigation}<main id="main-content">{body}</main></div>'
        f"<script>{SORT_SCRIPT}</script></body></html>"
    )


def write_report_files(
    folder: Path, markdown_text: str, report_date: date, config: ProjectConfig | None = None
) -> Path:
    markdown_path = folder / "report.md"
    markdown_path.write_text(markdown_text, encoding="utf-8")
    # The primary HTML is commonly downloaded, previewed, or shared without its
    # sibling assets directory. Keep it portable so charts survive those paths;
    # the WebP files remain alongside report.md for Markdown and chart reuse.
    document = _html_document(folder, markdown_text, embed_images=True)
    html_path = folder / report_html_name(report_date, config)
    html_path.write_text(document, encoding="utf-8")
    return html_path


def standalone_html_name(report_date: date, config: ProjectConfig | None = None) -> str:
    return f"{_report_file_prefix(config)}-{report_date.isoformat()}-standalone.html"


def write_standalone_report(folder: Path, report_date: date, destination: Path) -> Path:
    markdown_path = folder / "report.md"
    if not markdown_path.is_file():
        raise RuntimeError(f"Cannot export standalone report; missing {markdown_path}")
    document = _html_document(
        folder,
        markdown_path.read_text(encoding="utf-8"),
        embed_images=True,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return destination
