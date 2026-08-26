from __future__ import annotations

from datetime import date

import pytest

from ethanol_report.commodities import (
    format_change,
    format_price,
    format_tape_for_prompt,
    parse_yahoo_chart,
    scale_price,
    snapshot_contract,
)


def test_yahoo_corn_cents_are_scaled_to_dollars():
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1755129600, 1755734400],
                    "indicators": {"quote": [{"close": [400.0, 428.5]}]},
                }
            ]
        }
    }
    bars = parse_yahoo_chart(payload, unit="USD/bu")
    assert [row["close"] for row in bars] == [4.0, 4.285]
    assert scale_price(4.285, "USD/bu") == 4.285


def test_snapshot_uses_week_ago_close_and_formats_prompt():
    contract = {
        "id": "corn",
        "label": "Nearby corn",
        "yahoo_symbol": "ZC=F",
        "unit": "USD/bu",
    }
    bars = [
        {"date": date(2026, 8, 13), "close": 4.0},
        {"date": date(2026, 8, 20), "close": 4.285},
    ]
    row = snapshot_contract(contract, bars, date(2026, 8, 20))
    assert row is not None
    assert row["change"] == pytest.approx(0.285)
    assert format_price(row["last"], "USD/bu") == "$4.285/bu"
    assert format_change(row) == "+$0.285 (+7.1%)"
    prompt = format_tape_for_prompt([row], date(2026, 8, 20))
    assert "current perception of yield and demand risk" in prompt
    assert "Nearby corn (ZC=F): $4.285/bu as of 2026-08-20" in prompt
