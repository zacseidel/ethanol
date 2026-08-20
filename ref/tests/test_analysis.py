from __future__ import annotations

from datetime import date, timedelta

from healthcare_report.analysis import (
    Baseline,
    build_snapshot,
    compare_snapshots,
    min_ranks,
    months_before,
    notable_change_summary,
    price_base,
)


def bars(start: date, end: date, slope: float = 1.0):
    output = []
    current = start
    index = 0
    while current <= end:
        if current.weekday() < 5:
            output.append({"date": current, "close": 100 + index * slope})
        index += 1
        current += timedelta(days=1)
    return output


def test_month_arithmetic_and_base_tolerance():
    assert months_before(date(2024, 2, 29), 12) == date(2023, 2, 28)
    values = [{"date": date(2026, 1, 5), "close": 10.0}]
    assert price_base(values, date(2026, 1, 1), 7)["date"] == date(2026, 1, 5)
    assert price_base(values, date(2026, 1, 1), 2) is None


def test_ranks_use_competition_ranking():
    assert min_ranks({"A": 3.0, "B": 3.0, "C": 1.0, "D": None}) == {
        "A": 1,
        "B": 1,
        "C": 3,
        "D": None,
    }


def test_snapshot_has_all_three_rank_scopes(project):
    report_date = date(2026, 8, 3)
    history = {
        ticker: bars(date(2024, 7, 15), report_date, slope=index + 0.3)
        for index, ticker in enumerate(project.universe.companies)
    }
    reference = {
        ticker: {"market_cap": (index + 1) * 1_000_000_000}
        for index, ticker in enumerate(project.universe.companies)
    }
    snapshot, as_of = build_snapshot(project, report_date, history, reference)
    assert as_of == report_date
    category = next(row for row in snapshot if row["entity_type"] == "category")
    stock = next(row for row in snapshot if row["entity_type"] == "stock")
    assert category["rank"] is not None
    assert stock["overall_rank"] is not None
    assert stock["within_category_rank"] is not None


def test_comparison_uses_stored_ranks_instead_of_recomputed_intersection(project, tmp_path):
    old = [
        {
            "report_date": date(2026, 7, 27),
            "market_data_as_of": date(2026, 7, 24),
            "entity_type": "stock",
            "category": "Managed Care",
            "ticker": "UNH",
            "name": "UnitedHealth",
            "horizon_months": 3,
            "price_return": 0.10,
            "rank": 2,
            "overall_rank": 4,
            "within_category_rank": 2,
        }
    ]
    current = [
        {
            **old[0],
            "report_date": date(2026, 8, 3),
            "market_data_as_of": date(2026, 7, 31),
            "price_return": 0.15,
            "rank": 1,
            "overall_rank": 2,
            "within_category_rank": 1,
        }
    ]
    baseline = Baseline(
        tmp_path,
        old,
        {"report_date": "2026-07-27", "market_data_as_of": "2026-07-24"},
    )
    changes = compare_snapshots(current, baseline, project)
    within = next(row for row in changes if row["change_type"] == "within_category")
    overall = next(row for row in changes if row["change_type"] == "overall_stock")
    assert within["rank_delta"] == 1
    assert overall["rank_delta"] == 2


def test_notable_summary_is_capped_and_uses_the_configured_horizon(project):
    changes = []
    for index, (ticker, old_rank, new_rank) in enumerate(
        (("A", 1, 3), ("B", 2, 1), ("C", 3, 2), ("D", 20, 5))
    ):
        changes.append(
            {
                "change_type": "overall_stock",
                "ticker": ticker,
                "category": "Category",
                "name": f"Stock {ticker}",
                "horizon_months": 12,
                "previous_rank": old_rank,
                "current_rank": new_rank,
                "rank_delta": old_rank - new_rank,
                "previous_return": 0.1,
                "current_return": 0.2 + index / 100,
            }
        )
    for category, old_rank, new_rank in (
        ("Sector A", 1, 2),
        ("Sector B", 2, 1),
        ("Sector C", 3, 4),
        ("Sector D", 4, 1),
    ):
        changes.append(
            {
                "change_type": "category_performance",
                "category": category,
                "name": category,
                "horizon_months": 12,
                "previous_rank": old_rank,
                "current_rank": new_rank,
                "rank_delta": old_rank - new_rank,
                "previous_return": 0.1,
                "current_return": 0.2,
            }
        )

    summary = notable_change_summary(changes, project)
    assert summary["horizon_months"] == 12
    assert {row["ticker"] for row in summary["stocks"]["top"]} == {"A", "B", "C"}
    assert [row["ticker"] for row in summary["stocks"]["largest"]] == ["B", "A", "D"]
    assert [row["name"] for row in summary["categories"]["largest"]] == ["Sector D"]
