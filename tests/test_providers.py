from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx

from ethanol_report.cache import MarketCache
from ethanol_report.providers import MassiveClient, redact_secrets


def test_credentials_are_redacted():
    message = "failed https://api.massive.com/v2/aggs?apiKey=secret-value&limit=10"
    result = redact_secrets(message, ["secret-value"])
    assert "secret-value" not in result
    assert "apiKey=<redacted>" in result


def test_massive_pagination_skips_non_object_rows(project):
    project.settings["market_data"]["api_delay_seconds"] = 0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/first":
            return httpx.Response(
                200,
                json={
                    "results": [{"id": 1}, "bad"],
                    "next_url": "https://api.massive.com/second",
                },
            )
        return httpx.Response(200, json={"results": [{"id": 2}]})

    client = MassiveClient(project, api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        assert client.pages("/first") == [{"id": 1}, {"id": 2}]
    finally:
        client.close()


def test_massive_responses_are_checkpointed_and_reused(project):
    project.settings["market_data"]["api_delay_seconds"] = 0
    calls = {"company": 0, "prices": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v3/reference/tickers/UNH":
            calls["company"] += 1
            return httpx.Response(
                200,
                json={
                    "results": {
                        "name": "UnitedHealth",
                        "market_cap": 400_000_000_000,
                        "primary_exchange": "XNYS",
                    }
                },
            )
        if path.startswith("/v2/aggs/ticker/UNH/range/1/day/"):
            calls["prices"] += 1
            parts = path.split("/")
            start = date.fromisoformat(parts[-2])
            end = date.fromisoformat(parts[-1])
            rows = []
            current = start
            while current <= end:
                rows.append(
                    {
                        "t": int(
                            datetime.combine(current, datetime.min.time(), UTC).timestamp() * 1000
                        ),
                        "c": 100 + (current - start).days,
                    }
                )
                current += timedelta(days=1)
            return httpx.Response(200, json={"results": rows})
        raise AssertionError(f"unexpected request: {path}")

    transport = httpx.MockTransport(handler)
    first = MassiveClient(project, api_key="test-key", transport=transport)
    try:
        first.company("UNH")
        first.prices("UNH", date(2026, 1, 1), date(2026, 1, 2))
    finally:
        first.close()

    assert (project.root / "state" / "cache" / "companies.json").exists()
    assert (project.root / "state" / "cache" / "prices" / "UNH.json").exists()
    assert calls == {"company": 1, "prices": 1}

    resumed = MassiveClient(project, api_key="test-key", transport=transport)
    try:
        resumed.company("UNH")
        resumed.prices("UNH", date(2026, 1, 1), date(2026, 1, 2))
        assert resumed.last_source == "cache"
        resumed.prices("UNH", date(2026, 1, 1), date(2026, 1, 4))
        assert resumed.last_source == "cache+api"
    finally:
        resumed.close()

    assert calls == {"company": 1, "prices": 2}


def test_grouped_daily_prices_update_all_cached_tickers(project):
    project.settings["market_data"]["api_delay_seconds"] = 0
    grouped_calls: list[date] = []
    tickers = ["UNH", "CVS", "LLY"]

    def handler(request: httpx.Request) -> httpx.Response:
        prefix = "/v2/aggs/grouped/locale/us/market/stocks/"
        if not request.url.path.startswith(prefix):
            raise AssertionError(f"unexpected per-ticker request: {request.url.path}")
        market_date = date.fromisoformat(request.url.path.removeprefix(prefix))
        grouped_calls.append(market_date)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"T": ticker, "c": 100 + index + market_date.day}
                    for index, ticker in enumerate(tickers)
                ]
            },
        )

    client = MassiveClient(project, api_key="test-key", transport=httpx.MockTransport(handler))
    try:
        for ticker in tickers:
            client.cache.save_prices(
                ticker,
                {
                    "covered_start": "2026-01-01",
                    "covered_end": "2026-01-02",
                    "bars": [
                        {"date": date(2026, 1, 1), "close": 90},
                        {"date": date(2026, 1, 2), "close": 91},
                    ],
                },
            )
        client.prefetch_grouped_prices(tickers, date(2026, 1, 1), date(2026, 1, 6))
        for ticker in tickers:
            bars = client.prices(ticker, date(2026, 1, 1), date(2026, 1, 6))
            assert bars[-1]["date"] == date(2026, 1, 6)
            assert client.last_source == "cache"
    finally:
        client.close()

    assert grouped_calls == [date(2026, 1, 5), date(2026, 1, 6)]


def test_price_cache_retention_removes_only_old_bars(project):
    cache = MarketCache(project)
    cache.save_prices(
        "UNH",
        {
            "covered_start": "2024-01-01",
            "covered_end": "2026-08-03",
            "bars": [
                {"date": date(2024, 1, 1), "close": 90},
                {"date": date(2024, 7, 1), "close": 100},
                {"date": date(2026, 8, 3), "close": 110},
            ],
        },
    )
    result = cache.prune_prices(["UNH"], date(2024, 6, 1))
    assert result["bars_removed"] == 1
    assert [row["date"] for row in cache.price_bars("UNH")] == [
        date(2024, 7, 1),
        date(2026, 8, 3),
    ]
    assert cache.prices("UNH")["covered_start"] == "2024-07-01"
