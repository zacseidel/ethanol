from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from .cache import MarketCache
from .config import ProjectConfig


def redact_secrets(message: str, secrets: list[str] | None = None) -> str:
    output = message
    for secret in secrets or []:
        if secret:
            output = output.replace(secret, "<redacted>")
    return re.sub(r"([?&]apiKey=)[^&\s]+", r"\1<redacted>", output)


@dataclass
class FetchStatus:
    source: str
    subject: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "subject": self.subject,
            "status": self.status,
            "detail": self.detail,
        }


class MassiveClient:
    base_url = "https://api.massive.com"

    def __init__(
        self,
        config: ProjectConfig,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        candidate = api_key or os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY")
        if not candidate or candidate == "your_api_key_here":
            raise RuntimeError("MASSIVE_API_KEY is required")
        self.api_key: str = candidate
        self.config = config
        self.delay = float(config.settings["market_data"].get("api_delay_seconds", 13))
        self.company_cache_days = int(config.settings["market_data"].get("company_cache_days", 28))
        self.cache = MarketCache(config)
        self.last_source = ""
        self.last_status = "ok"
        self.last_detail = ""
        self._grouped_price_tickers: set[str] = set()
        self._grouped_price_error = ""
        self._last_request: float | None = None
        self.client = httpx.Client(
            timeout=httpx.Timeout(45, read=120),
            headers={"User-Agent": "healthcare-intel-digest/1.0"},
            transport=transport,
            follow_redirects=True,
        )

    def _trace(self, source: str, status: str, detail: str) -> None:
        self.last_source = source
        self.last_status = status
        self.last_detail = detail

    def close(self) -> None:
        self.client.close()

    def _wait(self) -> None:
        if self._last_request is None:
            return
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._wait()
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        query = dict(params or {})
        query["apiKey"] = self.api_key
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self._last_request = time.monotonic()
                response = self.client.get(url, params=query)
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise RuntimeError("provider returned a non-object JSON response")
                return body
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status not in {429, 500, 502, 503, 504} or attempt == 2:
                    break
                time.sleep(2**attempt)
        assert last_error is not None
        raise RuntimeError(redact_secrets(str(last_error), [self.api_key])) from last_error

    def pages(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while endpoint:
            body = self.get(endpoint, params)
            results = body.get("results", [])
            if isinstance(results, list):
                rows.extend(row for row in results if isinstance(row, dict))
            endpoint = str(body.get("next_url") or "")
            params = None
        return rows

    def company(self, ticker: str) -> dict[str, Any]:
        cached, fresh, age = self.cache.company(ticker, self.company_cache_days)
        if cached and fresh:
            self._trace("cache", "ok", f"reused company cache ({age} days old)")
            return cached
        try:
            result = self._fetch_company(ticker)
        except Exception as exc:
            if cached:
                self._trace(
                    "cache", "warning", f"reused stale company cache; refresh failed: {exc}"
                )
                return cached
            raise
        self.cache.save_company(ticker, result)
        self._trace("api", "ok", "fetched from Massive and cached")
        return result

    def _fetch_company(self, ticker: str) -> dict[str, Any]:
        body = self.get(f"/v3/reference/tickers/{ticker}")
        result = body.get("results")
        if not isinstance(result, dict):
            raise RuntimeError(f"{ticker} was not found at Massive")
        return {
            "ticker": ticker,
            "provider_name": result.get("name") or ticker,
            "market_cap": _number(result.get("market_cap")),
            "market_cap_date": date.today().isoformat(),
            "exchange": result.get("primary_exchange"),
            "list_date": result.get("list_date"),
            "description": result.get("description") or "",
            "website": result.get("homepage_url") or "",
        }

    def prices(self, ticker: str, start: date, end: date) -> list[dict[str, Any]]:
        record = self.cache.prices(ticker)
        cached_bars = self._parse_cached_bars(record)
        covered_start = _date(record.get("covered_start"))
        covered_end = _date(record.get("covered_end"))
        missing: list[tuple[date, date]] = []
        if covered_start is None or covered_end is None:
            missing.append((start, end))
        else:
            if start < covered_start:
                missing.append((start, covered_start - timedelta(days=1)))
            if end > covered_end:
                missing.append((covered_end + timedelta(days=1), end))
        if not missing:
            self._trace("cache", "ok", f"reused prices through {covered_end}")
            return _price_subset(cached_bars, start, end)

        if ticker in self._grouped_price_tickers and cached_bars:
            detail = "grouped price update was incomplete"
            if self._grouped_price_error:
                detail = f"{detail}: {self._grouped_price_error}"
            self._trace("cache", "warning", f"reused partial price cache; {detail}")
            return _price_subset(cached_bars, start, end)

        # If both ends are missing, one full-range request costs less than two shorter calls.
        if len(missing) > 1:
            missing = [(start, end)]

        had_cache = bool(cached_bars)
        for missing_start, missing_end in missing:
            try:
                fetched = self._fetch_prices(ticker, missing_start, missing_end)
            except Exception as exc:
                available = _price_subset(cached_bars, start, end)
                if available:
                    self._trace(
                        "cache",
                        "warning",
                        f"reused partial price cache; refresh failed: {exc}",
                    )
                    return available
                raise
            by_date = {row["date"]: row for row in cached_bars}
            by_date.update({row["date"]: row for row in fetched})
            cached_bars = [by_date[item] for item in sorted(by_date)]
            covered_start = min(covered_start or missing_start, missing_start)
            covered_end = max(covered_end or missing_end, missing_end)
            record.update(
                {
                    "covered_start": covered_start.isoformat(),
                    "covered_end": covered_end.isoformat(),
                    "bars": cached_bars,
                }
            )
            # Checkpoint every successful range immediately so Ctrl-C resumes here.
            self.cache.save_prices(ticker, record)

        source = "cache+api" if had_cache else "api"
        self._trace(source, "ok", f"cached prices through {covered_end}")
        return _price_subset(cached_bars, start, end)

    def prefetch_grouped_prices(
        self,
        tickers: list[str],
        start: date,
        end: date,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        eligible: dict[str, dict[str, Any]] = {}
        covered_ends: dict[str, date] = {}
        for ticker in tickers:
            record = self.cache.prices(ticker)
            covered_start = _date(record.get("covered_start"))
            covered_end = _date(record.get("covered_end"))
            if covered_start and covered_end and covered_start <= start and covered_end < end:
                eligible[ticker] = record
                covered_ends[ticker] = covered_end
        if not eligible:
            return

        first_missing = min(value + timedelta(days=1) for value in covered_ends.values())
        grouped_dates = [
            first_missing + timedelta(days=offset)
            for offset in range((end - first_missing).days + 1)
            if (first_missing + timedelta(days=offset)).weekday() < 5
        ]
        if not grouped_dates:
            for ticker, record in eligible.items():
                record["covered_end"] = end.isoformat()
                self.cache.save_prices(ticker, record)
            return
        if len(grouped_dates) >= len(eligible):
            return

        self._grouped_price_tickers.update(eligible)
        if progress:
            progress(
                f"Price update: using {len(grouped_dates)} grouped daily requests for "
                f"{len(eligible)} cached tickers."
            )
        completed = True
        for index, market_date in enumerate(grouped_dates, start=1):
            if progress:
                progress(
                    f"Grouped prices {index}/{len(grouped_dates)}: loading "
                    f"{market_date.isoformat()} for all tickers..."
                )
            try:
                daily = self._fetch_grouped_prices(market_date)
            except Exception as exc:
                completed = False
                self._grouped_price_error = str(exc)
                if progress:
                    progress(f"Grouped prices stopped at {market_date.isoformat()}: {exc}")
                break
            for ticker, record in eligible.items():
                if market_date <= covered_ends[ticker]:
                    continue
                cached_bars = self._parse_cached_bars(record)
                if ticker in daily:
                    by_date = {row["date"]: row for row in cached_bars}
                    by_date[market_date] = {"date": market_date, "close": daily[ticker]}
                    cached_bars = [by_date[item] for item in sorted(by_date)]
                record["bars"] = cached_bars
                record["covered_end"] = market_date.isoformat()
                covered_ends[ticker] = market_date
                self.cache.save_prices(ticker, record)

        if completed:
            for ticker, record in eligible.items():
                record["covered_end"] = end.isoformat()
                self.cache.save_prices(ticker, record)
            if progress:
                progress(f"Grouped price update complete through {end.isoformat()}.")

    def _fetch_grouped_prices(self, market_date: date) -> dict[str, float]:
        body = self.get(
            f"/v2/aggs/grouped/locale/us/market/stocks/{market_date.isoformat()}",
            {"adjusted": "true"},
        )
        rows = body.get("results", [])
        output: dict[str, float] = {}
        if not isinstance(rows, list):
            return output
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("T") or "")
            close = _number(row.get("c"))
            if ticker and close is not None and close > 0:
                output[ticker] = close
        return output

    def _fetch_prices(self, ticker: str, start: date, end: date) -> list[dict[str, Any]]:
        rows = self.pages(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        output: list[dict[str, Any]] = []
        for row in rows:
            try:
                timestamp = datetime.fromtimestamp(float(row["t"]) / 1000, tz=UTC)
                close = float(row["c"])
            except (KeyError, TypeError, ValueError, OSError):
                continue
            if close > 0:
                output.append({"date": timestamp.date(), "close": close})
        return output

    @staticmethod
    def _parse_cached_bars(record: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in record.get("bars", []):
            if not isinstance(row, dict):
                continue
            parsed_date = _date(row.get("date"))
            close = _number(row.get("close"))
            if parsed_date and close is not None and close > 0:
                output.append({"date": parsed_date, "close": close})
        return sorted(output, key=lambda row: row["date"])


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _price_subset(bars: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    return [row for row in bars if start <= row["date"] <= end]


class BrowserSession:
    """One anonymous Chromium page shared by earnings and narrative scrapers."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self.page: Any = None

    def __enter__(self) -> BrowserSession:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed") from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self.page = self._browser.new_page(locale="en-US")
        return self

    def html(self, url: str, wait_ms: int = 2500) -> str:
        if self.page is None:
            raise RuntimeError("browser session is not open")
        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self.page.wait_for_timeout(wait_ms)
        return str(self.page.content())

    def __exit__(self, *_: Any) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
