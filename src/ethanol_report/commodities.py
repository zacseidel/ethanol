from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from .analysis import price_on_or_before
from .config import ProjectConfig
from .providers import FetchStatus, redact_secrets
from .storage import read_json, utc_now, write_json

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}

DEFAULT_CONTRACTS: tuple[dict[str, str], ...] = (
    {
        "id": "corn",
        "label": "Nearby corn",
        "yahoo_symbol": "ZC=F",
        "unit": "USD/bu",
    },
    {
        "id": "ethanol",
        "label": "CBOT ethanol",
        "yahoo_symbol": "EH=F",
        "unit": "USD/gal",
    },
    {
        "id": "rbob",
        "label": "RBOB gasoline",
        "yahoo_symbol": "RB=F",
        "unit": "USD/gal",
    },
    {
        "id": "natgas",
        "label": "Henry Hub",
        "yahoo_symbol": "NG=F",
        "unit": "USD/MMBtu",
    },
)


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def cache_slug(symbol: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in symbol).strip("-")


def contract_list(config: ProjectConfig | None = None) -> list[dict[str, str]]:
    configured: list[Any] = []
    if config is not None:
        raw = config.settings.get("commodity_tape", {})
        if isinstance(raw, dict):
            configured = raw.get("contracts") or []
    rows = configured if isinstance(configured, list) and configured else list(DEFAULT_CONTRACTS)
    output: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("yahoo_symbol") or "").strip()
        label = str(row.get("label") or "").strip()
        if not symbol or not label:
            continue
        output.append(
            {
                "id": str(row.get("id") or cache_slug(symbol)),
                "label": label,
                "yahoo_symbol": symbol,
                "unit": str(row.get("unit") or "").strip(),
            }
        )
    return output


def scale_price(raw: float, unit: str) -> float:
    """Yahoo corn is usually cents/bu (e.g. 428.5). Display dollars when the unit is USD/bu."""
    if unit == "USD/bu" and raw >= 50:
        return raw / 100.0
    return raw


def parse_yahoo_chart(payload: dict[str, Any], *, unit: str = "") -> list[dict[str, Any]]:
    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(results, list) or not results:
        return []
    first = results[0]
    if not isinstance(first, dict):
        return []
    timestamps = first.get("timestamp")
    indicators = first.get("indicators") if isinstance(first.get("indicators"), dict) else {}
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    closes = quotes[0].get("close") if isinstance(quotes, list) and quotes else None
    if not isinstance(timestamps, list) or not isinstance(closes, list):
        return []
    output: list[dict[str, Any]] = []
    for stamp, close in zip(timestamps, closes, strict=False):
        try:
            bar_date = datetime.fromtimestamp(float(stamp), tz=UTC).date()
            raw = float(close)
        except (TypeError, ValueError, OSError):
            continue
        if raw <= 0:
            continue
        output.append({"date": bar_date, "close": scale_price(raw, unit)})
    return sorted({row["date"]: row for row in output}.values(), key=lambda row: row["date"])


def snapshot_contract(
    contract: dict[str, str],
    bars: list[dict[str, Any]],
    report_date: date,
) -> dict[str, Any] | None:
    current = price_on_or_before(bars, report_date)
    if not current:
        return None
    prior = price_on_or_before(bars, report_date - timedelta(days=7))
    last = round(float(current["close"]), 6)
    last_date = current["date"]
    prior_close = round(float(prior["close"]), 6) if prior else None
    prior_date = prior["date"] if prior else None
    if prior_date == last_date:
        prior_close = None
        prior_date = None
    change = round(last - prior_close, 6) if prior_close is not None else None
    change_pct = (
        round(change / prior_close, 6) if change is not None and prior_close else None
    )
    return {
        "id": contract["id"],
        "label": contract["label"],
        "yahoo_symbol": contract["yahoo_symbol"],
        "unit": contract["unit"],
        "last": last,
        "last_date": last_date.isoformat() if isinstance(last_date, date) else str(last_date),
        "prior": prior_close,
        "prior_date": prior_date.isoformat() if isinstance(prior_date, date) else None,
        "change": change,
        "change_pct": change_pct,
    }


def format_price(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "USD/bu":
        return f"${value:.3f}/bu"
    if unit in {"USD/gal", "USD/MMBtu"}:
        return f"${value:.3f}/{unit.split('/')[-1]}"
    return f"${value:.3f}"


def format_change(row: dict[str, Any]) -> str:
    change = row.get("change")
    percent = row.get("change_pct")
    if change is None:
        return "n/a"
    unit = str(row.get("unit") or "")
    sign = "+" if change >= 0 else "-"
    magnitude = abs(float(change))
    if unit == "USD/bu":
        signed = f"{sign}${magnitude:.3f}"
    else:
        signed = f"{sign}{magnitude:.3f}"
    if percent is None:
        return signed
    return f"{signed} ({percent:+.1%})"


def format_tape_for_prompt(tape: list[dict[str, Any]], report_date: date) -> str:
    if not tape:
        return ""
    lines = [
        f'<market_tape as_of="{report_date.isoformat()}">',
        "These nearby futures are retrieved independently of web search. Nearby corn is the",
        "market's current perception of yield and demand risk. The Executive View lead on corn",
        "must be consistent with the corn change below; quote the last price and weekly change.",
    ]
    for row in tape:
        last = format_price(row.get("last"), str(row.get("unit") or ""))
        prior = format_price(row.get("prior"), str(row.get("unit") or ""))
        change = format_change(row)
        prior_date = row.get("prior_date") or "n/a"
        lines.append(
            f"- {row['label']} ({row['yahoo_symbol']}): {last} as of {row['last_date']}; "
            f"week change {change} from {prior} on {prior_date}."
        )
    lines.append("</market_tape>")
    return "\n".join(lines)


def _cache_path(config: ProjectConfig, symbol: str):
    return config.root / "state" / "cache" / "commodities" / f"{cache_slug(symbol)}.json"


def _cached_bars(config: ProjectConfig, symbol: str) -> list[dict[str, Any]]:
    record = read_json(_cache_path(config, symbol), {})
    if not isinstance(record, dict):
        return []
    output: list[dict[str, Any]] = []
    for row in record.get("bars", []):
        if not isinstance(row, dict):
            continue
        bar_date = _as_date(row.get("date"))
        raw_close = row.get("close")
        try:
            close = float(raw_close) if raw_close is not None else None
        except (TypeError, ValueError):
            continue
        if bar_date and close is not None and close > 0:
            output.append({"date": bar_date, "close": close})
    return sorted(output, key=lambda item: item["date"])


def _save_bars(config: ProjectConfig, symbol: str, bars: list[dict[str, Any]]) -> None:
    write_json(
        _cache_path(config, symbol),
        {
            "schema": 1,
            "yahoo_symbol": symbol,
            "updated_at": utc_now(),
            "bars": [
                {
                    "date": row["date"].isoformat()
                    if isinstance(row["date"], date)
                    else str(row["date"]),
                    "close": float(row["close"]),
                }
                for row in bars
            ],
        },
    )


def fetch_yahoo_daily_bars(
    symbol: str,
    start: date,
    end: date,
    *,
    client: httpx.Client | None = None,
    unit: str = "",
) -> list[dict[str, Any]]:
    period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=UTC).timestamp())
    period2 = int(
        datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC).timestamp()
    )
    owns_client = client is None
    session = client or httpx.Client(timeout=30, follow_redirects=True, headers=YAHOO_HEADERS)
    try:
        response = session.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            params={"period1": period1, "period2": period2, "interval": "1d"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Yahoo chart returned a non-object JSON response")
        return parse_yahoo_chart(payload, unit=unit)
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        raise RuntimeError(redact_secrets(str(exc))) from exc
    finally:
        if owns_client:
            session.close()


def load_commodity_tape(
    config: ProjectConfig,
    report_date: date,
    *,
    client: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], list[FetchStatus]]:
    start = report_date - timedelta(days=21)
    tape: list[dict[str, Any]] = []
    statuses: list[FetchStatus] = []
    for contract in contract_list(config):
        symbol = contract["yahoo_symbol"]
        cached = _cached_bars(config, symbol)
        covered_end = cached[-1]["date"] if cached else None
        if covered_end is None or covered_end < report_date:
            try:
                fetched = fetch_yahoo_daily_bars(
                    symbol,
                    start,
                    report_date,
                    client=client,
                    unit=contract["unit"],
                )
            except Exception as exc:
                statuses.append(
                    FetchStatus("Yahoo Finance", symbol, "warning", str(exc))
                )
                fetched = []
            if fetched:
                by_date = {row["date"]: row for row in cached}
                by_date.update({row["date"]: row for row in fetched})
                cached = [by_date[item] for item in sorted(by_date)]
                _save_bars(config, symbol, cached)
                statuses.append(
                    FetchStatus(
                        "Yahoo Finance",
                        symbol,
                        "ok",
                        f"cached prices through {cached[-1]['date'].isoformat()}",
                    )
                )
            elif cached:
                statuses.append(
                    FetchStatus(
                        "Yahoo Finance",
                        symbol,
                        "warning",
                        f"reused partial cache through {cached[-1]['date'].isoformat()}",
                    )
                )
        else:
            statuses.append(
                FetchStatus(
                    "Yahoo Finance",
                    symbol,
                    "ok",
                    f"reused prices through {covered_end.isoformat()}",
                )
            )
        snapshot = snapshot_contract(contract, cached, report_date)
        if snapshot:
            tape.append(snapshot)
        elif not any(item.subject == symbol for item in statuses):
            statuses.append(
                FetchStatus("Yahoo Finance", symbol, "warning", "no usable nearby bars")
            )
    return tape, statuses
