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
    assert (
        report_html_name(date(2026, 8, 3), project)
        == "Weekly Corn and Ethanol Intel Report-2026-08-03.html"
    )
    assert standalone_html_name(date(2026, 8, 3), project).startswith(
        "Weekly Corn and Ethanol Intel Report-"
    )
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


def test_generate_strategy_farmer_does_not_clobber_narrative(project, monkeypatch, capsys):
    import ethanol_report.farmer as farmer_module
    import ethanol_report.site as site_module

    state = project.root / "state"
    state.mkdir(exist_ok=True)
    narrative = state / "narrative.json"
    narrative.write_text('{"body": "ethanol narrative"}\n', encoding="utf-8")

    def fake_farmer_strategy(_config, report_date, *, profile=None, force=False, **_kwargs):
        assert profile == "farmer"
        return {
            "status": "success",
            "report_type": "farmer",
            "report_date": report_date.isoformat(),
            "generated_at": f"{report_date.isoformat()}T12:00:00Z",
            "model": "gpt-5.6-sol",
            "content_markdown": (
                "# Farmer Corn Brief\n## Week of August 24, 2026\n\n"
                "The board paid you this week.\n"
            ),
        }

    monkeypatch.setattr(farmer_module, "generate_strategy_report", fake_farmer_strategy)
    monkeypatch.setattr(site_module, "build_site", lambda _config, output=None: {"status": "ok"})
    monkeypatch.chdir(project.root)
    assert main(["generate-strategy", "--report", "farmer", "--date", "2026-08-24"]) == 0
    assert narrative.read_text(encoding="utf-8") == '{"body": "ethanol narrative"}\n'
    farmer_html = (
        project.root
        / "reports"
        / "final"
        / "farmer"
        / "2026-08-24"
        / "Farmer Corn Brief-2026-08-24.html"
    )
    assert farmer_html.is_file()
    assert "The board paid you this week" in farmer_html.read_text()
    assert '"report_type": "farmer"' in capsys.readouterr().out


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
