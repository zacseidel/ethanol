from __future__ import annotations

from datetime import date

from healthcare_report.earnings import (
    apply_tentative,
    parse_google_earnings,
    refresh_needed,
)


def test_tentative_event_is_day_90_and_recheck_is_day_69(project):
    record = apply_tentative({"last_report_date": "2026-04-30"}, project)
    assert record["next_event_date"] == "2026-07-29"
    assert record["next_check_date"] == "2026-07-08"
    assert record["next_date_status"] == "tentative"
    assert not refresh_needed(record, date(2026, 7, 7), project)
    assert refresh_needed(record, date(2026, 7, 8), project)


def test_confirmed_date_rechecks_in_final_three_weeks(project):
    record = {
        "last_report_date": "2026-04-30",
        "next_event_date": "2026-08-30",
        "next_date_status": "confirmed",
    }
    assert not refresh_needed(record, date(2026, 8, 8), project)
    assert refresh_needed(record, date(2026, 8, 9), project)


def test_same_report_date_is_not_retried_twice_in_one_day(project):
    record = {
        "checked_at": "2026-08-04T12:00:00Z",
        "checked_for_date": "2026-08-03",
    }
    assert not refresh_needed(
        record,
        date(2026, 8, 3),
        project,
        checked_on=date(2026, 8, 4),
    )
    assert refresh_needed(
        record,
        date(2026, 8, 10),
        project,
        checked_on=date(2026, 8, 4),
    )


def test_google_parser_keeps_last_and_next_dates_separate():
    html = """
    <html><body><div>Last report Apr 30, 2026</div><div>Next earnings Aug 5, 2026</div>
    <div><span>Call transcript</span><p>summarize_auto Adjusted EPS increased meaningfully.</p></div>
    <section><h2>At a glance</h2>
      <div class="sgb2mf"><strong class="mFa7Bd">Revenue:</strong>
      <span class="KBDbl">Revenue exceeded expectations.</span></div>
    </section></body></html>
    """
    result = parse_google_earnings(html, "LLY", date(2026, 7, 20))
    assert result["last_report_date"] == "2026-04-30"
    assert result["next_event_date"] == "2026-08-05"
    assert result["summary"] == "Adjusted EPS increased meaningfully."
    assert result["at_a_glance_scope"] == "reported"
    assert result["at_a_glance"] == [
        {"headline": "Revenue", "detail": "Revenue exceeded expectations."}
    ]
