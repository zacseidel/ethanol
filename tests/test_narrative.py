from __future__ import annotations

from datetime import date

from ethanol_report.narrative import (
    narrative_refresh_needed,
    refresh_narrative,
    refresh_narrative_with_fallback,
)
from ethanol_report.storage import read_json


def test_ethanol_refresh_uses_openai_archive(project, monkeypatch):
    import ethanol_report.narrative as narrative

    report_date = date(2026, 8, 24)

    def fake_generate(config, generated_for, *, force=False, **_kwargs):
        assert config.scope == "ethanol"
        assert generated_for == report_date
        assert not force
        return {
            "report_date": report_date.isoformat(),
            "generated_at": "2026-08-24T14:00:00Z",
            "model": "gpt-5.6-sol",
            "content_markdown": """# Ethanol Strategy Brief
## Week of August 24, 2026

## Executive View
- Material crush-margin delta.
""",
        }

    monkeypatch.setattr(narrative, "generate_strategy_report", fake_generate)
    result = refresh_narrative(project, as_of=report_date)

    assert result["source_type"] == "openai_responses"
    assert result["checked_for_date"] == "2026-08-24"
    assert result["body"].startswith("### Executive View")
    assert "Ethanol Strategy Brief" not in result["body"]


def test_narrative_same_day_refresh_is_reused():
    cached = {
        "checked_for_date": "2026-08-03",
        "fetched_at": "2026-08-04T12:00:00Z",
    }
    assert not narrative_refresh_needed(
        cached,
        date(2026, 8, 3),
        checked_on=date(2026, 8, 4),
    )
    assert narrative_refresh_needed(
        cached,
        date(2026, 8, 10),
        checked_on=date(2026, 8, 4),
    )


def test_failed_narrative_refresh_is_retried_on_the_same_day(project, monkeypatch):
    import ethanol_report.narrative as narrative

    def fail_refresh(*_args, **_kwargs):
        raise RuntimeError("fixture outage")

    monkeypatch.setattr(narrative, "refresh_narrative", fail_refresh)
    value, status, detail = refresh_narrative_with_fallback(
        project,
        None,
        as_of=date(2026, 8, 3),
        checked_on=date(2026, 8, 4),
    )
    assert value is None
    assert status == "warning"
    assert detail == "fixture outage"
    marker = read_json(project.root / "state" / "narrative.json")
    assert marker["checked_on"] == "2026-08-04"
    assert marker["last_check_error"] == "fixture outage"
    assert narrative_refresh_needed(
        marker,
        date(2026, 8, 3),
        checked_on=date(2026, 8, 4),
    )
