from __future__ import annotations

import html
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .commodities import load_commodity_tape
from .config import ProjectConfig
from .render import (
    _commodity_tape_markup,
    _corn_meta_line,
    _long_date,
    _narrative_created,
    _strip_status_labels,
    write_report_files,
)
from .storage import atomic_replace_directory, utc_now, write_json
from .strategy import generate_strategy_report

FARMER_REPORT_NAME = "Farmer Corn Brief"
FARMER_PROFILE = "farmer"


def farmer_final_root(config: ProjectConfig) -> Path:
    return config.root / "reports" / "final" / FARMER_PROFILE


def build_farmer_markdown(
    body: str,
    report_date: date,
    tape: list[dict[str, Any]],
    generated_at: str = "",
) -> str:
    content = _strip_status_labels(body.strip())
    meta_bits = [f"<strong>Week of {_long_date(report_date)}</strong>"]
    corn = _corn_meta_line(tape)
    if corn:
        meta_bits.append(html.escape(corn))
    created = _narrative_created({"fetched_at": generated_at}) if generated_at else None
    if created:
        meta_bits.append(f"Narrative created: {html.escape(created)}")
    meta = (
        '<div class="report-meta">'
        + "".join(f"<span>{item}</span>" for item in meta_bits)
        + "</div>"
    )
    extras = [meta, ""]
    tape_markup = _commodity_tape_markup(tape).rstrip()
    if tape_markup:
        extras.extend([tape_markup, ""])

    lines = content.splitlines()
    insert_at = 0
    if lines and re.match(r"^#\s+", lines[0]):
        insert_at = 1
        if len(lines) > 1 and re.match(r"^##\s+Week of", lines[1], flags=re.I):
            insert_at = 2
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
    return "\n".join([*lines[:insert_at], "", *extras, *lines[insert_at:]]).strip() + "\n"


def publish_farmer_brief(
    config: ProjectConfig,
    report_date: date,
    result: dict[str, Any],
    commodity_tape: list[dict[str, Any]] | None = None,
) -> Path:
    body = str(result.get("content_markdown") or "").strip()
    if not body:
        raise RuntimeError("Cannot publish a farmer brief without report content")
    tape = [dict(row) for row in (commodity_tape or []) if isinstance(row, dict)]
    markdown_text = build_farmer_markdown(
        body,
        report_date,
        tape,
        str(result.get("generated_at") or ""),
    )
    final_root = farmer_final_root(config)
    final_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".farmer-{report_date.isoformat()}-", dir=final_root))
    try:
        html_name = f"{FARMER_REPORT_NAME}-{report_date.isoformat()}.html"
        write_report_files(
            temporary,
            markdown_text,
            report_date,
            report_name=FARMER_REPORT_NAME,
        )
        corn = next((row for row in tape if row.get("id") == "corn"), None)
        market_as_of = str((corn or {}).get("last_date") or report_date.isoformat())[:10]
        write_json(
            temporary / "manifest.json",
            {
                "schema": 2,
                "report_type": FARMER_PROFILE,
                "report_name": FARMER_REPORT_NAME,
                "report_date": report_date.isoformat(),
                "market_data_as_of": market_as_of,
                "generated_at": result.get("generated_at") or utc_now(),
                "rendered_at": utc_now(),
                "quality": "ok",
                "issues": [],
                "sources": [
                    {
                        "source": "farmer brief",
                        "subject": "OpenAI Responses API",
                        "status": str(result.get("status") or "ok"),
                        "detail": str(result.get("model") or result.get("detail") or ""),
                    }
                ],
                "files": [html_name, "report.md", "manifest.json"],
            },
        )
        destination = final_root / report_date.isoformat()
        atomic_replace_directory(temporary, destination)
        return destination
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def generate_farmer_brief(
    config: ProjectConfig,
    report_date: date,
    *,
    force: bool = False,
    dry_run: bool = False,
    commodity_tape: list[dict[str, Any]] | None = None,
    response_client: Any | None = None,
) -> dict[str, Any]:
    result = generate_strategy_report(
        config,
        report_date,
        profile=FARMER_PROFILE,
        force=force,
        dry_run=dry_run,
        commodity_tape=commodity_tape,
        response_client=response_client,
    )
    if dry_run or not result.get("content_markdown"):
        return result
    tape = commodity_tape
    if tape is None:
        tape, _statuses = load_commodity_tape(config, report_date)
    publish_farmer_brief(config, report_date, result, tape)
    return result
