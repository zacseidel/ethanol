from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .config import ProjectConfig
from .providers import BrowserSession, FetchStatus
from .storage import read_json, utc_now, write_json

EXCHANGE_NAMES = {
    "XNYS": "NYSE",
    "XNAS": "NASDAQ",
    "XASE": "NYSEAMERICAN",
    "ARCX": "NYSEARCA",
    "BATS": "BATS",
}
MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DISPLAY_DATE = re.compile(rf"{MONTH}\s+\d{{1,2}}(?:,\s*\d{{4}})?", re.I)
ICON_LIGATURES = re.compile(r"\b(?:summarize_auto|insights_auto|expand_more|search_spark)\b")


def earnings_state_path(config: ProjectConfig) -> Path:
    return config.root / "state" / "earnings.json"


def load_earnings_state(config: ProjectConfig) -> dict[str, dict[str, Any]]:
    value = read_json(earnings_state_path(config), {})
    return value if isinstance(value, dict) else {}


def parse_display_date(value: str, as_of: date) -> date | None:
    match = DISPLAY_DATE.search(value)
    if not match:
        return None
    text = match.group(0)
    has_year = bool(re.search(r"\d{4}", text))
    if not has_year:
        text = f"{text}, {as_of.year}"
    for pattern in ("%b %d, %Y", "%B %d, %Y"):
        try:
            parsed = datetime.strptime(text, pattern).date()
            if not has_year and parsed < as_of - timedelta(days=180):
                parsed = parsed.replace(year=parsed.year + 1)
            return parsed
        except ValueError:
            continue
    return None


def _date_after_label(text: str, labels: tuple[str, ...], as_of: date) -> date | None:
    lower = text.lower()
    for label in labels:
        position = lower.find(label.lower())
        if position >= 0:
            value = parse_display_date(
                text[position + len(label) : position + len(label) + 140], as_of
            )
            if value:
                return value
    return None


def strip_icon_ligatures(value: str) -> str:
    return " ".join(ICON_LIGATURES.sub("", value).split())


def _parse_at_a_glance(soup: BeautifulSoup) -> tuple[list[dict[str, str]], str | None]:
    headings = soup.find_all(
        string=lambda item: isinstance(item, str) and item.strip().lower().startswith("at a glance")
    )
    for text_node in headings:
        heading_text = text_node.strip()
        node = text_node.parent
        for _level in range(4):
            if node is None or node.name in ("body", "html"):
                break
            cards = node.select(".sgb2mf")
            insights: list[dict[str, str]] = []
            for card in cards:
                headline_node = card.select_one(".mFa7Bd")
                detail_node = card.select_one(".KBDbl")
                detail = strip_icon_ligatures(
                    detail_node.get_text(" ", strip=True) if detail_node else ""
                )
                if not detail:
                    continue
                headline = strip_icon_ligatures(
                    headline_node.get_text(" ", strip=True) if headline_node else ""
                ).rstrip(":")
                insights.append({"headline": headline, "detail": detail})
            if not insights:
                for bullet in node.find_all("li"):
                    detail = strip_icon_ligatures(bullet.get_text(" ", strip=True))
                    if len(detail) >= 20:
                        insights.append({"headline": "", "detail": detail})
            if insights:
                scope = "upcoming" if "upcoming" in heading_text.lower() else "reported"
                return insights, scope
            node = node.parent
    return [], None


def parse_google_earnings(html: str, ticker: str, as_of: date) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    latest = _date_after_label(text, ("Last report", "Previous report"), as_of)
    upcoming = _date_after_label(text, ("Next call", "Next earnings"), as_of)

    summary = ""
    label = soup.find(
        string=lambda item: isinstance(item, str) and item.strip() == "Call transcript"
    )
    if label and label.parent and label.parent.parent:
        candidates = [
            " ".join(node.get_text(" ", strip=True).split())
            for node in label.parent.parent.find_all(recursive=False)
        ]
        candidates = [item for item in candidates if item and item != "Call transcript"]
        if candidates:
            summary = strip_icon_ligatures(max(candidates, key=len))

    moments: list[dict[str, str]] = []
    for card in soup.select(".B1GkSe"):
        title = card.select_one(".tDiKLc")
        timestamp = card.select_one(".kcbpeb")
        blurb = card.select_one(".h3qzgf")
        if title and timestamp and blurb:
            moments.append(
                {
                    "title": title.get_text(" ", strip=True),
                    "timestamp": timestamp.get_text(" ", strip=True),
                    "blurb": blurb.get_text(" ", strip=True),
                }
            )
    at_a_glance, glance_scope = _parse_at_a_glance(soup)
    if not any((latest, upcoming, summary, moments, at_a_glance)):
        raise RuntimeError("Google Finance earnings labels were not found")
    return {
        "ticker": ticker,
        "last_report_date": latest.isoformat() if latest else None,
        "next_event_date": upcoming.isoformat() if upcoming else None,
        "summary": summary,
        "key_moments": moments,
        "at_a_glance": at_a_glance,
        "at_a_glance_scope": glance_scope,
    }


def fetch_yahoo_date(ticker: str, as_of: date) -> date | None:
    response = httpx.get(
        f"https://finance.yahoo.com/quote/{ticker}/",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    label = soup.find(string=lambda item: isinstance(item, str) and item.strip() == "Earnings Date")
    if not label or not label.parent or not label.parent.parent:
        return None
    return parse_display_date(label.parent.parent.get_text(" ", strip=True), as_of)


def google_url(ticker: str, exchange: str | None) -> str:
    google_exchange = EXCHANGE_NAMES.get(str(exchange), "NYSE")
    return f"https://www.google.com/finance/quote/{ticker}:{google_exchange}?tab=earnings&hl=en"


def next_check_date(record: dict[str, Any], config: ProjectConfig) -> date | None:
    last = _as_date(record.get("last_report_date"))
    if not last:
        return None
    interval = int(config.settings["earnings"].get("tentative_interval_days", 90))
    lead = int(config.settings["earnings"].get("tentative_check_lead_days", 21))
    return last + timedelta(days=interval - lead)


def refresh_needed(
    record: dict[str, Any] | None,
    as_of: date,
    config: ProjectConfig,
    *,
    checked_on: date | None = None,
) -> bool:
    checked_on = checked_on or datetime.now(UTC).date()
    checked_at = _as_datetime(record.get("checked_at")) if record else None
    if (
        record
        and record.get("checked_for_date") == as_of.isoformat()
        and checked_at
        and checked_at.date() == checked_on
    ):
        return False
    if not record or not _as_date(record.get("last_report_date")):
        return True
    last = _as_date(record.get("last_report_date"))
    window = int(config.settings["earnings"].get("window_days", 7))
    if (
        last
        and last >= as_of - timedelta(days=window)
        and (record.get("summary") or record.get("key_moments"))
        and not record.get("at_a_glance_checked_at")
    ):
        return True
    status = record.get("next_date_status")
    event = _as_date(record.get("next_event_date"))
    if status == "tentative":
        check = _as_date(record.get("next_check_date")) or next_check_date(record, config)
        return check is None or as_of >= check
    if status == "confirmed" and event:
        lead = int(config.settings["earnings"].get("confirmed_recheck_lead_days", 21))
        return as_of >= event - timedelta(days=lead)
    return True


def apply_tentative(record: dict[str, Any], config: ProjectConfig) -> dict[str, Any]:
    last = _as_date(record.get("last_report_date"))
    if not last or record.get("next_event_date"):
        return record
    interval = int(config.settings["earnings"].get("tentative_interval_days", 90))
    lead = int(config.settings["earnings"].get("tentative_check_lead_days", 21))
    record["next_event_date"] = (last + timedelta(days=interval)).isoformat()
    record["next_check_date"] = (last + timedelta(days=interval - lead)).isoformat()
    record["next_date_status"] = "tentative"
    record["next_date_source"] = "estimated from last earnings"
    return record


def refresh_earnings(
    config: ProjectConfig,
    as_of: date,
    companies: dict[str, dict[str, Any]],
    browser: BrowserSession | None,
    progress: Callable[[str], None] | None = None,
    *,
    state: dict[str, dict[str, Any]] | None = None,
    checked_on: date | None = None,
    force: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[FetchStatus]]:
    source_state = state if state is not None else load_earnings_state(config)
    checked_on = checked_on or datetime.now(UTC).date()
    output = {
        ticker: dict(record) for ticker, record in source_state.items() if isinstance(record, dict)
    }
    statuses: list[FetchStatus] = []
    total = len(config.universe.companies)
    for index, ticker in enumerate(config.universe.companies, start=1):
        old = output.get(ticker, {})
        if not force and not refresh_needed(old, as_of, config, checked_on=checked_on):
            if progress:
                progress(f"Earnings {index}/{total}: {ticker} recheck is not due; using cache.")
            output[ticker] = apply_tentative(old, config)
            statuses.append(FetchStatus("earnings", ticker, "skipped", "not due for recheck"))
            continue
        parsed: dict[str, Any] | None = None
        error = ""
        if progress:
            progress(f"Earnings {index}/{total}: checking {ticker}...")
        if browser is not None:
            try:
                parsed = parse_google_earnings(
                    browser.html(google_url(ticker, companies.get(ticker, {}).get("exchange"))),
                    ticker,
                    as_of,
                )
            except Exception as exc:  # a secondary scraper failure must not cancel prices
                error = str(exc)
        record = dict(old)
        if parsed:
            for key in ("last_report_date", "summary", "key_moments"):
                if parsed.get(key):
                    record[key] = parsed[key]
            record["summary"] = strip_icon_ligatures(str(record.get("summary") or ""))
            record["at_a_glance_checked_at"] = utc_now()
            record["at_a_glance_scope"] = parsed.get("at_a_glance_scope")
            if parsed.get("at_a_glance_scope") == "reported":
                record["at_a_glance"] = parsed.get("at_a_glance") or []
                record["at_a_glance_report_date"] = parsed.get("last_report_date")
            if parsed.get("next_event_date"):
                record["next_event_date"] = parsed["next_event_date"]
                record["next_date_status"] = "confirmed"
                record["next_date_source"] = "Google Finance"
                record["next_check_date"] = None
        if not parsed or not parsed.get("next_event_date"):
            try:
                yahoo = fetch_yahoo_date(ticker, as_of)
            except Exception as exc:
                yahoo = None
                error = "; ".join(item for item in (error, str(exc)) if item)
            if yahoo:
                record["next_event_date"] = yahoo.isoformat()
                record["next_date_status"] = "confirmed"
                record["next_date_source"] = "Yahoo Finance"
                record["next_check_date"] = None
        record["checked_at"] = utc_now()
        record["checked_for_date"] = as_of.isoformat()
        output[ticker] = apply_tentative(record, config)
        status = "ok" if parsed else "warning"
        if not record.get("last_report_date") and not record.get("next_event_date"):
            status = "warning"
            error = error or "no earnings dates were available"
        statuses.append(FetchStatus("earnings", ticker, status, error))
    return output, statuses


def save_earnings_state(config: ProjectConfig, state: dict[str, dict[str, Any]]) -> None:
    write_json(earnings_state_path(config), state)


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
