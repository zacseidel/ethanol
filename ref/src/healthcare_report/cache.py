from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from .config import ProjectConfig
from .storage import read_csv, read_json, utc_now, write_json


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _as_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


class MarketCache:
    """Durable, credential-free provider cache committed with report state."""

    def __init__(self, config: ProjectConfig) -> None:
        self.root = config.root / "state" / "cache"
        self.legacy_root = config.root / "data"

    def company(
        self, ticker: str, max_age_days: int
    ) -> tuple[dict[str, Any] | None, bool, int | None]:
        document = read_json(self.root / "companies.json", {"schema": 1, "companies": {}})
        companies = document.get("companies", {}) if isinstance(document, dict) else {}
        record = companies.get(ticker) if isinstance(companies, dict) else None
        if not isinstance(record, dict):
            record = self._legacy_company(ticker)
            if record:
                self.save_company(ticker, record["value"], str(record["fetched_at"]))
        if not isinstance(record, dict) or not isinstance(record.get("value"), dict):
            return None, False, None
        fetched = _as_datetime(record.get("fetched_at"))
        age = (datetime.now(UTC).date() - fetched.date()).days if fetched else None
        fresh = age is not None and 0 <= age <= max_age_days
        return dict(record["value"]), fresh, age

    def save_company(
        self, ticker: str, value: dict[str, Any], fetched_at: str | None = None
    ) -> None:
        path = self.root / "companies.json"
        document = read_json(path, {"schema": 1, "companies": {}})
        if not isinstance(document, dict):
            document = {"schema": 1, "companies": {}}
        companies = document.setdefault("companies", {})
        if not isinstance(companies, dict):
            companies = {}
            document["companies"] = companies
        companies[ticker] = {"fetched_at": fetched_at or utc_now(), "value": value}
        write_json(path, document)

    def reference(self) -> dict[str, dict[str, Any]]:
        document = read_json(self.root / "companies.json", {"schema": 1, "companies": {}})
        companies = document.get("companies", {}) if isinstance(document, dict) else {}
        if not isinstance(companies, dict):
            return {}
        return {
            str(ticker): dict(record["value"])
            for ticker, record in companies.items()
            if isinstance(record, dict) and isinstance(record.get("value"), dict)
        }

    def prices(self, ticker: str) -> dict[str, Any]:
        path = self.root / "prices" / f"{ticker}.json"
        record = read_json(path)
        if isinstance(record, dict) and isinstance(record.get("bars"), list):
            return record
        legacy = self._legacy_prices(ticker)
        if legacy:
            self.save_prices(ticker, legacy)
            return legacy
        return {"schema": 1, "ticker": ticker, "bars": []}

    def save_prices(self, ticker: str, record: dict[str, Any]) -> None:
        output = dict(record)
        output.update({"schema": 1, "ticker": ticker, "updated_at": utc_now()})
        output["bars"] = sorted(
            (
                {
                    "date": row["date"].isoformat()
                    if isinstance(row["date"], date)
                    else str(row["date"]),
                    "close": float(row["close"]),
                }
                for row in record.get("bars", [])
                if _as_date(row.get("date")) and _number(row.get("close")) is not None
            ),
            key=lambda row: row["date"],
        )
        write_json(self.root / "prices" / f"{ticker}.json", output)

    def price_bars(
        self, ticker: str, start: date | None = None, end: date | None = None
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in self.prices(ticker).get("bars", []):
            if not isinstance(row, dict):
                continue
            parsed_date = _as_date(row.get("date"))
            close = _number(row.get("close"))
            if not parsed_date or close is None or close <= 0:
                continue
            if start and parsed_date < start:
                continue
            if end and parsed_date > end:
                continue
            output.append({"date": parsed_date, "close": close})
        return sorted(output, key=lambda row: row["date"])

    def prune_prices(self, tickers: list[str], cutoff: date) -> dict[str, int | str]:
        files_changed = 0
        bars_removed = 0
        bars_retained = 0
        for ticker in tickers:
            record = self.prices(ticker)
            original = [row for row in record.get("bars", []) if isinstance(row, dict)]
            retained = [
                row for row in original if (_as_date(row.get("date")) or date.min) >= cutoff
            ]
            bars_removed += len(original) - len(retained)
            bars_retained += len(retained)
            if len(retained) == len(original):
                continue
            updated = dict(record)
            updated["bars"] = retained
            if retained:
                updated["covered_start"] = min(str(row["date"]) for row in retained)
            self.save_prices(ticker, updated)
            files_changed += 1
        return {
            "cutoff": cutoff.isoformat(),
            "files_changed": files_changed,
            "bars_removed": bars_removed,
            "bars_retained": bars_retained,
        }

    def _legacy_company(self, ticker: str) -> dict[str, Any] | None:
        for row in read_csv(self.legacy_root / "companies.csv"):
            if row.get("ticker") != ticker:
                continue
            return {
                "fetched_at": row.get("updated_at") or row.get("market_cap_date"),
                "value": {
                    "ticker": ticker,
                    "provider_name": row.get("provider_name") or ticker,
                    "market_cap": _number(row.get("market_cap")),
                    "market_cap_date": row.get("market_cap_date"),
                    "exchange": row.get("exchange"),
                    "list_date": row.get("list_date") or None,
                    "description": row.get("provider_description") or "",
                    "website": row.get("website") or "",
                },
            }
        return None

    def _legacy_prices(self, ticker: str) -> dict[str, Any] | None:
        bars: list[dict[str, Any]] = []
        for row in read_csv(self.legacy_root / "prices" / f"{ticker}.csv"):
            parsed_date = _as_date(row.get("date"))
            close = _number(row.get("close"))
            if parsed_date and close is not None and close > 0:
                bars.append({"date": parsed_date.isoformat(), "close": close})
        if not bars:
            return None
        dates = sorted(str(row["date"]) for row in bars)
        return {
            "schema": 1,
            "ticker": ticker,
            "covered_start": dates[0],
            "covered_end": dates[-1],
            "updated_at": utc_now(),
            "bars": bars,
        }
