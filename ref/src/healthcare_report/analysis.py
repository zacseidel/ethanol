from __future__ import annotations

import calendar
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .storage import read_csv, read_json

SNAPSHOT_FIELDS = [
    "report_date",
    "market_data_as_of",
    "entity_type",
    "category",
    "ticker",
    "name",
    "horizon_months",
    "price_return",
    "rank",
    "overall_rank",
    "within_category_rank",
    "market_cap",
    "market_cap_coverage",
    "price_date",
]

CHANGE_FIELDS = [
    "change_type",
    "entity_type",
    "category",
    "ticker",
    "name",
    "horizon_months",
    "previous_rank",
    "current_rank",
    "rank_delta",
    "previous_return",
    "current_return",
    "return_delta",
    "previous_report_date",
    "current_report_date",
    "detail",
]


@dataclass
class Baseline:
    folder: Path
    snapshot: list[dict[str, Any]]
    manifest: dict[str, Any]

    @property
    def report_date(self) -> date:
        return date.fromisoformat(str(self.manifest["report_date"]))

    @property
    def market_data_as_of(self) -> date:
        value = self.manifest.get("market_data_as_of") or self.manifest["report_date"]
        return date.fromisoformat(str(value))


def months_before(value: date, months: int) -> date:
    total = value.year * 12 + value.month - 1 - months
    year, zero_month = divmod(total, 12)
    month = zero_month + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def price_on_or_before(bars: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    eligible = [bar for bar in bars if bar["date"] <= target and float(bar["close"]) > 0]
    return max(eligible, key=lambda item: item["date"]) if eligible else None


def price_base(
    bars: list[dict[str, Any]], target: date, tolerance_days: int
) -> dict[str, Any] | None:
    before = price_on_or_before(bars, target)
    if before:
        return before
    eligible = [
        bar
        for bar in bars
        if target < bar["date"] <= target + timedelta(days=tolerance_days)
        and float(bar["close"]) > 0
    ]
    return min(eligible, key=lambda item: item["date"]) if eligible else None


def ticker_returns(
    ticker: str,
    bars: list[dict[str, Any]],
    report_date: date,
    horizons: Iterable[int],
    tolerance_days: int,
) -> list[dict[str, Any]]:
    ending = price_on_or_before(bars, report_date)
    rows: list[dict[str, Any]] = []
    for horizon in horizons:
        starting = price_base(bars, months_before(report_date, int(horizon)), tolerance_days)
        value = None
        if starting and ending:
            value = float(ending["close"]) / float(starting["close"]) - 1
        rows.append(
            {
                "ticker": ticker,
                "horizon_months": int(horizon),
                "price_return": value,
                "price_date": ending["date"] if ending else None,
                "start_date": starting["date"] if starting else None,
            }
        )
    return rows


def min_ranks(values: dict[str, float | None]) -> dict[str, int | None]:
    ordered = sorted(
        ((key, value) for key, value in values.items() if value is not None),
        key=lambda item: (-float(item[1]), item[0]),
    )
    ranks: dict[str, int | None] = {key: None for key in values}
    previous: float | None = None
    rank = 0
    for position, (key, value) in enumerate(ordered, start=1):
        if previous is None or not math.isclose(
            float(value), previous, rel_tol=1e-12, abs_tol=1e-15
        ):
            rank = position
        ranks[key] = rank
        previous = float(value)
    return ranks


def weighted_return(rows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    total_cap = sum(float(row["market_cap"]) for row in rows if row.get("market_cap"))
    eligible = [
        row for row in rows if row.get("market_cap") and row.get("price_return") is not None
    ]
    eligible_cap = sum(float(row["market_cap"]) for row in eligible)
    if not eligible_cap:
        return None, 0.0 if total_cap else None
    value = sum(float(row["price_return"]) * float(row["market_cap"]) for row in eligible)
    return value / eligible_cap, eligible_cap / total_cap if total_cap else None


def build_snapshot(
    config: ProjectConfig,
    report_date: date,
    bars: dict[str, list[dict[str, Any]]],
    reference: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], date]:
    horizons = [int(item) for item in config.settings["report"]["return_horizons_months"]]
    tolerance = int(config.settings["market_data"].get("price_base_tolerance_days", 7))
    returns: dict[tuple[str, int], dict[str, Any]] = {}
    for ticker in config.universe.companies:
        for row in ticker_returns(ticker, bars.get(ticker, []), report_date, horizons, tolerance):
            returns[(ticker, row["horizon_months"])] = row
    price_dates = [row["price_date"] for row in returns.values() if row.get("price_date")]
    if not price_dates:
        raise RuntimeError("No configured company has a usable current market price")
    market_data_as_of = max(price_dates)

    overall_by_horizon: dict[int, dict[str, int | None]] = {}
    for horizon in horizons:
        overall_by_horizon[horizon] = min_ranks(
            {
                ticker: returns[(ticker, horizon)]["price_return"]
                for ticker in config.universe.companies
            }
        )

    stock_rows: list[dict[str, Any]] = []
    for category, members in config.universe.categories.items():
        for horizon in horizons:
            category_ranks = min_ranks(
                {
                    company.ticker: returns[(company.ticker, horizon)]["price_return"]
                    for company in members
                }
            )
            for company in members:
                result = returns[(company.ticker, horizon)]
                company_reference = reference.get(company.ticker, {})
                stock_rows.append(
                    {
                        "report_date": report_date,
                        "market_data_as_of": market_data_as_of,
                        "entity_type": "stock",
                        "category": category,
                        "ticker": company.ticker,
                        "name": company.name,
                        "horizon_months": horizon,
                        "price_return": result["price_return"],
                        "rank": category_ranks[company.ticker],
                        "overall_rank": overall_by_horizon[horizon][company.ticker],
                        "within_category_rank": category_ranks[company.ticker],
                        "market_cap": company_reference.get("market_cap"),
                        "market_cap_coverage": 1.0
                        if company_reference.get("market_cap")
                        and result["price_return"] is not None
                        else 0.0,
                        "price_date": result["price_date"],
                    }
                )

    category_rows: list[dict[str, Any]] = []
    pending: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for category in config.universe.categories:
        for horizon in horizons:
            category_members = [
                row
                for row in stock_rows
                if row["category"] == category and row["horizon_months"] == horizon
            ]
            value, coverage = weighted_return(category_members)
            pending[horizon].append(
                {
                    "report_date": report_date,
                    "market_data_as_of": market_data_as_of,
                    "entity_type": "category",
                    "category": category,
                    "ticker": "",
                    "name": category,
                    "horizon_months": horizon,
                    "price_return": value,
                    "overall_rank": None,
                    "within_category_rank": None,
                    "market_cap": sum(
                        float(row["market_cap"])
                        for row in category_members
                        if row.get("market_cap")
                    )
                    or None,
                    "market_cap_coverage": coverage,
                    "price_date": min(
                        (row["price_date"] for row in category_members if row.get("price_date")),
                        default=None,
                    ),
                }
            )
    for _horizon, rows in pending.items():
        ranks = min_ranks({row["category"]: row["price_return"] for row in rows})
        for row in rows:
            row["rank"] = ranks[row["category"]]
            category_rows.append(row)
    return sorted(
        category_rows + stock_rows,
        key=lambda row: (
            row["entity_type"],
            int(row["horizon_months"]),
            row["rank"] if row["rank"] is not None else 9999,
            row["category"],
            row["ticker"],
        ),
    ), market_data_as_of


def find_baseline(config: ProjectConfig, report_date: date) -> Baseline | None:
    root = config.final_root
    if not root.exists():
        return None
    minimum = int(config.settings["report"].get("previous_report_minimum_days", 5))
    candidates: list[tuple[date, Path]] = []
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        try:
            candidate_date = date.fromisoformat(folder.name)
        except ValueError:
            continue
        if candidate_date <= report_date - timedelta(days=minimum):
            candidates.append((candidate_date, folder))
    for _, folder in sorted(candidates, reverse=True):
        snapshot = read_csv(folder / "snapshot.csv")
        manifest = read_json(folder / "manifest.json", {})
        report_type = str(manifest.get("report_type") or "healthcare")
        if (
            snapshot
            and isinstance(manifest, dict)
            and manifest.get("report_date")
            and report_type == config.scope
        ):
            return Baseline(folder, [coerce_snapshot(row) for row in snapshot], manifest)
    return None


def compare_snapshots(
    current: list[dict[str, Any]], baseline: Baseline | None, config: ProjectConfig
) -> list[dict[str, Any]]:
    current_report_date = current[0]["report_date"] if current else date.today()
    if baseline is None:
        return [
            {
                "change_type": "baseline",
                "entity_type": "report",
                "category": "",
                "ticker": "",
                "name": "First report",
                "horizon_months": None,
                "previous_rank": None,
                "current_rank": None,
                "rank_delta": None,
                "previous_return": None,
                "current_return": None,
                "return_delta": None,
                "previous_report_date": None,
                "current_report_date": current_report_date,
                "detail": "No earlier final report is available; this report establishes the baseline.",
            }
        ]
    changes: list[dict[str, Any]] = []
    previous = baseline.snapshot

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        if row["entity_type"] == "category":
            return ("category", row["category"], int(row["horizon_months"]))
        return ("stock", row["category"], row["ticker"], int(row["horizon_months"]))

    before = {key(row): row for row in previous}
    now = {key(row): row for row in current}
    for entity_key in sorted(set(before) & set(now), key=str):
        old, new = before[entity_key], now[entity_key]
        old_rank = _integer(old.get("rank"))
        new_rank = _integer(new.get("rank"))
        old_return = _float(old.get("price_return"))
        new_return = _float(new.get("price_return"))
        changes.append(
            _change_row(
                "category_performance" if new["entity_type"] == "category" else "within_category",
                new,
                old_rank,
                new_rank,
                old_return,
                new_return,
                baseline.report_date,
                current_report_date,
            )
        )

    def unique_overall(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
        result: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            if row["entity_type"] == "stock":
                result.setdefault((row["ticker"], int(row["horizon_months"])), row)
        return result

    old_overall, new_overall = unique_overall(previous), unique_overall(current)
    for entity_key in sorted(set(old_overall) & set(new_overall)):
        old, new = old_overall[entity_key], new_overall[entity_key]
        changes.append(
            _change_row(
                "overall_stock",
                {**new, "category": ""},
                _integer(old.get("overall_rank")),
                _integer(new.get("overall_rank")),
                _float(old.get("price_return")),
                _float(new.get("price_return")),
                baseline.report_date,
                current_report_date,
            )
        )

    old_memberships = {
        (row["category"], row["ticker"], row["name"])
        for row in previous
        if row["entity_type"] == "stock"
    }
    new_memberships = {
        (row["category"], row["ticker"], row["name"])
        for row in current
        if row["entity_type"] == "stock"
    }
    for change_type, memberships in (
        ("watchlist_added", new_memberships - old_memberships),
        ("watchlist_removed", old_memberships - new_memberships),
    ):
        for category, ticker, name in sorted(memberships):
            verb = "added to" if change_type.endswith("added") else "removed from"
            changes.append(
                {
                    "change_type": change_type,
                    "entity_type": "membership",
                    "category": category,
                    "ticker": ticker,
                    "name": name,
                    "horizon_months": None,
                    "previous_rank": None,
                    "current_rank": None,
                    "rank_delta": None,
                    "previous_return": None,
                    "current_return": None,
                    "return_delta": None,
                    "previous_report_date": baseline.report_date,
                    "current_report_date": current_report_date,
                    "detail": f"{name} ({ticker}) was {verb} {category}.",
                }
            )
    return changes


def _change_row(
    change_type: str,
    row: dict[str, Any],
    previous_rank: int | None,
    current_rank: int | None,
    previous_return: float | None,
    current_return: float | None,
    previous_date: date,
    current_date: date,
) -> dict[str, Any]:
    rank_delta = (
        previous_rank - current_rank
        if previous_rank is not None and current_rank is not None
        else None
    )
    return_delta = (
        current_return - previous_return
        if previous_return is not None and current_return is not None
        else None
    )
    detail = _change_detail(
        change_type,
        row,
        previous_rank,
        current_rank,
        previous_return,
        current_return,
    )
    return {
        "change_type": change_type,
        "entity_type": row["entity_type"],
        "category": row.get("category", ""),
        "ticker": row.get("ticker", ""),
        "name": row["name"],
        "horizon_months": row.get("horizon_months"),
        "previous_rank": previous_rank,
        "current_rank": current_rank,
        "rank_delta": rank_delta,
        "previous_return": previous_return,
        "current_return": current_return,
        "return_delta": return_delta,
        "previous_report_date": previous_date,
        "current_report_date": current_date,
        "detail": detail,
    }


def _change_detail(
    change_type: str,
    row: dict[str, Any],
    previous_rank: int | None,
    current_rank: int | None,
    previous_return: float | None,
    current_return: float | None,
) -> str:
    horizon = row.get("horizon_months")
    rank_text = (
        f"rank #{previous_rank} to #{current_rank}"
        if previous_rank is not None and current_rank is not None
        else "rank unavailable"
    )
    return_text = (
        f"return {format_percent(previous_return)} to {format_percent(current_return)}"
        if previous_return is not None and current_return is not None
        else "return unavailable"
    )
    scope = {
        "category_performance": "among subcategories",
        "within_category": f"within {row.get('category')}",
        "overall_stock": "across the watchlist",
    }.get(change_type, "")
    return f"{row['name']} moved from {rank_text} {scope} at {horizon} months; {return_text}."


def notable_change_summary(
    changes: list[dict[str, Any]], config: ProjectConfig
) -> dict[str, Any]:
    settings = config.settings["notable_changes"]
    horizon = int(settings.get("comparison_horizon_months", 12))
    top_n = int(settings.get("top_n", 3))
    largest_n = int(settings.get("largest_rank_changes", 3))

    def rows(change_type: str) -> list[dict[str, Any]]:
        return [
            row
            for row in changes
            if row.get("change_type") == change_type
            and row.get("horizon_months") == horizon
            and row.get("previous_rank") is not None
            and row.get("current_rank") is not None
        ]

    def summary_for(change_type: str) -> dict[str, list[dict[str, Any]]]:
        ranked = rows(change_type)
        top = [
            row
            for row in ranked
            if min(int(row["previous_rank"]), int(row["current_rank"])) <= top_n
        ]
        top.sort(key=lambda row: (min(row["previous_rank"], row["current_rank"]), row["name"]))
        minimum_change = 2 if change_type == "category_performance" else 1
        largest = sorted(
            (
                row
                for row in ranked
                if row.get("rank_delta") and abs(float(row["rank_delta"])) >= minimum_change
            ),
            key=lambda row: (
                -abs(float(row["rank_delta"])),
                row["current_rank"],
                row["name"],
            ),
        )[:largest_n]
        top.sort(key=lambda row: (row["current_rank"], row["name"]))
        largest.sort(key=lambda row: (row["current_rank"], row["name"]))
        return {"top": top, "largest": largest}

    stock_summary = summary_for("overall_stock")
    category_summary = summary_for("category_performance")
    selected: dict[tuple[str, str, int], dict[str, Any]] = {}
    for group in (stock_summary, category_summary):
        for rows_for_group in group.values():
            for row in rows_for_group:
                selected[
                    (
                        str(row.get("change_type")),
                        str(row.get("ticker") or row.get("category") or row.get("name")),
                        int(row["horizon_months"]),
                    )
                ] = row
    selected_items = list(selected.values())
    selected_items.sort(key=lambda row: (row["change_type"], row["current_rank"], row["name"]))
    selected_items.extend(
        row
        for row in changes
        if row.get("change_type") in {"baseline", "watchlist_added", "watchlist_removed"}
    )
    return {
        "horizon_months": horizon,
        "top_n": top_n,
        "stocks": stock_summary,
        "categories": category_summary,
        "items": selected_items,
    }


def notable_changes(changes: list[dict[str, Any]], config: ProjectConfig) -> list[dict[str, Any]]:
    """Return the capped rows retained for the report's notable-change section."""
    return notable_change_summary(changes, config)["items"]


def period_moves(
    config: ProjectConfig,
    bars: dict[str, list[dict[str, Any]]],
    reference: dict[str, dict[str, Any]],
    baseline: Baseline | None,
    report_date: date,
) -> dict[str, Any]:
    if baseline is None:
        return {"stocks": [], "categories": []}
    stock_rows: list[dict[str, Any]] = []
    for ticker, company in config.universe.companies.items():
        start = price_on_or_before(bars.get(ticker, []), baseline.market_data_as_of)
        end = price_on_or_before(bars.get(ticker, []), report_date)
        move = None if not start or not end else float(end["close"]) / float(start["close"]) - 1
        stock_rows.append(
            {
                "ticker": ticker,
                "name": company.name,
                "price_move": move,
                "market_cap": reference.get(ticker, {}).get("market_cap"),
            }
        )
    category_rows = []
    for category, members in config.universe.categories.items():
        member_rows = [
            row for row in stock_rows if row["ticker"] in {item.ticker for item in members}
        ]
        weighted, coverage = weighted_return(
            [{**row, "price_return": row["price_move"]} for row in member_rows]
        )
        category_rows.append(
            {"category": category, "price_move": weighted, "market_cap_coverage": coverage}
        )
    return {"stocks": stock_rows, "categories": category_rows}


def data_issues(
    config: ProjectConfig,
    snapshot: list[dict[str, Any]],
    statuses: list[dict[str, str]],
    narrative_age_days: int | None,
) -> list[str]:
    issues: list[str] = []
    max_age = int(config.settings["market_data"].get("maximum_price_age_days", 7))
    report_date = snapshot[0]["report_date"]
    stock_latest: dict[str, date | None] = {}
    for row in snapshot:
        if row["entity_type"] == "stock":
            stock_latest.setdefault(row["ticker"], row.get("price_date"))
    stale = [
        ticker
        for ticker, value in stock_latest.items()
        if value is None or (report_date - value).days > max_age
    ]
    if stale:
        issues.append(f"Stale or missing prices: {', '.join(stale)}.")
    minimum = float(config.settings["market_data"].get("minimum_market_cap_coverage", 0.8))
    low = [
        f"{row['category']} {row['horizon_months']}m"
        for row in snapshot
        if row["entity_type"] == "category"
        and (row.get("market_cap_coverage") is None or row["market_cap_coverage"] < minimum)
    ]
    if low:
        issues.append(f"Low market-cap coverage: {', '.join(low)}.")
    failures = [
        f"{row['source']}:{row['subject']} ({row.get('detail') or row['status']})"
        for row in statuses
        if row["status"] not in {"ok", "skipped"}
    ]
    if failures:
        issues.append("Secondary source warnings: " + "; ".join(failures))
    stale_after = int(config.settings["strategy_narrative"].get("stale_after_days", 7))
    if narrative_age_days is None:
        issues.append("No strategy narrative retrieval date is available.")
    elif narrative_age_days > stale_after:
        issues.append(f"Strategy narrative was retrieved {narrative_age_days} days ago.")
    return issues


def format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1%}"


def load_snapshot(path: Path) -> list[dict[str, Any]]:
    return [coerce_snapshot(row) for row in read_csv(path)]


def coerce_snapshot(row: dict[str, str]) -> dict[str, Any]:
    output: dict[str, Any] = dict(row)
    for field in ("report_date", "market_data_as_of", "price_date"):
        output[field] = date.fromisoformat(row[field]) if row.get(field) else None
    for field in ("horizon_months", "rank", "overall_rank", "within_category_rank"):
        output[field] = _integer(row.get(field))
    for field in ("price_return", "market_cap", "market_cap_coverage"):
        output[field] = _float(row.get(field))
    return output


def _integer(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        result = float(value) if value not in (None, "") else None
        return None if result is not None and math.isnan(result) else result
    except (TypeError, ValueError):
        return None
