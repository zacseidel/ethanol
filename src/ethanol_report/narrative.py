from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .providers import BrowserSession
from .storage import read_json, utc_now, write_json
from .strategy import (
    generate_strategy_report,
    load_latest_published_strategy,
    load_latest_strategy,
)


def narrative_path(config: ProjectConfig) -> Path:
    default = str(config.settings.get("report", {}).get("slug") or config.scope)
    if config.scope == default:
        return config.root / "state" / "narrative.json"
    return config.root / "state" / f"narrative-{config.report_slug}.json"


def load_narrative(config: ProjectConfig) -> dict[str, Any] | None:
    try:
        value = read_json(narrative_path(config))
    except RuntimeError:
        value = None
    if not isinstance(value, dict):
        latest = load_latest_strategy(config) or load_latest_published_strategy(config)
        if latest:
            generated_at = str(latest.get("generated_at") or "")
            value = {
                "schema": 3,
                "source_type": "openai_responses",
                "fetched_at": generated_at,
                "checked_at": generated_at,
                "checked_on": generated_at[:10],
                "checked_for_date": str(latest.get("report_date") or ""),
                "period": _human_date(str(latest.get("report_date") or "")),
                "body": _embedded_strategy_body(str(latest.get("content_markdown") or "")),
                "model": latest.get("model"),
                "response_id": latest.get("response_id"),
                "usage": latest.get("usage"),
                "estimated_cost_usd": latest.get("estimated_cost_usd"),
            }
    if not isinstance(value, dict):
        return None
    value = dict(value)
    value["body"] = clean_cached_markdown(str(value.get("body") or ""))
    return value


def _human_date(value: str) -> str | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return f"{parsed:%B} {parsed.day}, {parsed.year}"


def _embedded_strategy_body(body: str) -> str:
    """Remove the standalone title and nest its sections inside the full market report."""
    embedded = re.sub(
        r"^#\s+Ethanol Strategy Brief\s*\n+",
        "",
        body.strip(),
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    embedded = re.sub(
        r"^##\s+Week of[^\n]*\n+",
        "",
        embedded,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    return re.sub(
        r"^(#{2,5})(\s+)",
        lambda match: f"{match.group(1)}#{match.group(2)}",
        embedded,
        flags=re.MULTILINE,
    )


def clean_cached_markdown(body: str) -> str:
    """Clean snapshots written by the former raw-innerHTML exporter."""
    body = re.sub(
        r'<div class="mb-1 mt-6" testid="nav-list-widget">.*$',
        "",
        body,
        flags=re.DOTALL,
    )
    body = re.sub(
        r'<span state="closed">.*?<a href="([^"]+)".*?</a></span></span>',
        lambda match: f" [source]({match.group(1)})",
        body,
        flags=re.DOTALL,
    )
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def refresh_narrative(
    config: ProjectConfig,
    browser: BrowserSession | None = None,
    *,
    as_of: date | None = None,
    force: bool = False,
    commodity_tape: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report_date = as_of or datetime.now(config.timezone).date()
    generated = generate_strategy_report(
        config,
        report_date,
        force=force,
        commodity_tape=commodity_tape,
    )
    generated_at = str(generated.get("generated_at") or utc_now())
    value = {
        "schema": 3,
        "source_type": "openai_responses",
        "fetched_at": generated_at,
        "checked_at": utc_now(),
        "checked_on": datetime.now(UTC).date().isoformat(),
        "checked_for_date": report_date.isoformat(),
        "period": _human_date(report_date.isoformat()),
        "body": _embedded_strategy_body(str(generated.get("content_markdown") or "")),
        "model": generated.get("model"),
        "response_id": generated.get("response_id"),
        "prompt_sha256": generated.get("prompt_sha256"),
        "usage": generated.get("usage"),
        "estimated_cost_usd": generated.get("estimated_cost_usd"),
    }
    if not value["body"]:
        raise RuntimeError("OpenAI strategy archive did not contain report content")
    write_json(narrative_path(config), value)
    return value


def refresh_narrative_with_fallback(
    config: ProjectConfig,
    browser: BrowserSession | None,
    *,
    as_of: date,
    checked_on: date | None = None,
    force: bool = False,
    commodity_tape: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, str, str]:
    cached = load_narrative(config)
    if not force and not narrative_refresh_needed(cached, as_of, checked_on=checked_on):
        return cached, "skipped", "already refreshed for this report date today"
    try:
        refreshed = refresh_narrative(
            config,
            browser,
            as_of=as_of,
            force=force,
            commodity_tape=commodity_tape,
        )
        return refreshed, "ok", "OpenAI Responses API"
    except Exception as exc:
        checked_on = checked_on or datetime.now(UTC).date()
        check_record = dict(cached or {})
        check_record.update(
            {
                "schema": 2,
                "checked_at": utc_now(),
                "checked_on": checked_on.isoformat(),
                "checked_for_date": as_of.isoformat(),
                "last_check_error": str(exc),
            }
        )
        write_json(narrative_path(config), check_record)
        if cached:
            return check_record, "warning", str(exc)
        return None, "warning", str(exc)


def narrative_refresh_needed(
    narrative: dict[str, Any] | None,
    as_of: date,
    *,
    checked_on: date | None = None,
) -> bool:
    if not narrative or narrative.get("checked_for_date") != as_of.isoformat():
        return True
    if narrative.get("last_check_error"):
        return True
    checked_on = checked_on or datetime.now(UTC).date()
    if narrative.get("checked_on") == checked_on.isoformat():
        return False
    try:
        checked = datetime.fromisoformat(
            str(narrative.get("checked_at") or narrative.get("fetched_at") or "").replace(
                "Z", "+00:00"
            )
        )
    except ValueError:
        return True
    return checked.astimezone(UTC).date() != checked_on


def narrative_age(narrative: dict[str, Any] | None, as_of: date) -> int | None:
    if not narrative or not narrative.get("fetched_at"):
        return None
    try:
        fetched = datetime.fromisoformat(str(narrative["fetched_at"]).replace("Z", "+00:00"))
        return (as_of - fetched.astimezone(UTC).date()).days
    except ValueError:
        return None
