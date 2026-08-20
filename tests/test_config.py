from __future__ import annotations

from datetime import date

import pytest

from ethanol_report.cli import main, parse_date
from ethanol_report.config import (
    ConfigurationError,
    load_config,
)


def test_current_universe_is_valid(project):
    assert project.universe.categories
    assert project.universe.companies
    assert all(project.universe.categories.values())
    assert str(project.timezone) == "America/Chicago"


def test_single_ethanol_profile_uses_root_outputs(project):
    from ethanol_report.narrative import narrative_path
    from ethanol_report.render import report_html_name, standalone_html_name

    assert project.scope == "ethanol"
    assert "GPRE" in project.universe.companies
    assert "VLO" in project.universe.companies
    assert project.final_root == project.root / "reports" / "final"
    assert report_html_name(date(2026, 8, 3), project) == "Corn and Ethanol Intel-2026-08-03.html"
    assert standalone_html_name(date(2026, 8, 3), project).startswith("Corn and Ethanol Intel-")
    assert narrative_path(project).name == "narrative.json"


def test_cli_date_is_strict():
    assert parse_date("2026-08-03") == date(2026, 8, 3)
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        parse_date("August 3")


def test_conflicting_company_metadata_is_rejected(project):
    categories = project.universe.categories
    first = next(iter(categories.values()))[0]
    from ethanol_report.config import Company, Universe

    universe = Universe({"One": (first,), "Two": (Company(first.ticker, "Wrong", "Wrong"),)})
    with pytest.raises(ConfigurationError, match="conflicting"):
        _ = universe.companies


def test_companies_markdown_drives_categories(project):
    path = project.root / "inputs" / "companies.md"
    path.write_text(
        """---
Payers:
  HUM: Humana; Medicare-focused health insurer.
Cross-category:
  HUM: Humana; Medicare-focused health insurer.
  VEEV: Veeva; Cloud software for life-sciences companies.
---

# Companies
This prose is ignored by the configuration reader.
""",
        encoding="utf-8",
    )
    updated = load_config(project.root)
    assert list(updated.universe.categories) == ["Payers", "Cross-category"]
    assert set(updated.universe.companies) == {"HUM", "VEEV"}
    assert updated.universe.categories["Payers"][0].description.startswith("Medicare")


def test_companies_markdown_requires_requested_line_format(project):
    path = project.root / "inputs" / "companies.md"
    path.write_text("---\nPayers:\n  HUM: Humana with no separator\n---\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Ticker: Name; Description"):
        load_config(project.root)


def test_chatgpt_share_file_is_no_longer_a_configuration_input(project):
    path = project.root / "inputs" / "strategy-narratives.md"
    path.write_text("This retired file is not parsed.\n", encoding="utf-8")

    updated = load_config(project.root)
    assert "url" not in updated.settings["strategy_narrative"]
    assert "url" not in updated.for_scope("ethanol").settings["strategy_narrative"]


def test_refresh_narrative_cli_selects_ethanol_profile(project, monkeypatch, capsys):
    import ethanol_report.narrative as narrative

    path = project.root / "inputs" / "strategy-narratives.md"
    original = path.read_text(encoding="utf-8")
    seen: list[str] = []

    def fake_refresh(config):
        seen.append(config.scope)
        return {"status": "ok"}

    monkeypatch.setattr(narrative, "refresh_narrative", fake_refresh)
    monkeypatch.chdir(project.root)
    assert main(["refresh-narrative", "--report", "ethanol"]) == 0
    assert seen == ["ethanol"]
    assert path.read_text(encoding="utf-8") == original
    assert '"status": "ok"' in capsys.readouterr().out
