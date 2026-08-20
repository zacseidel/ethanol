from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ethanol_report.config import load_config


@pytest.fixture(autouse=True)
def stub_site_pdf_generation(monkeypatch):
    import ethanol_report.site as site

    def publish_downloads(reports, destination, _previous_site=None):
        for report in reports:
            folder = destination / "reports" / report.archive_path
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report.source, folder / f"{report.source.stem}.html")
            (folder / f"{report.source.stem}.pdf").write_bytes(b"%PDF-1.4\nfixture\n")

    monkeypatch.setattr(site, "_publish_report_downloads", publish_downloads)


@pytest.fixture
def project(tmp_path: Path):
    source = Path(__file__).resolve().parents[1]
    shutil.copy(source / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copytree(source / "config", tmp_path / "config")
    shutil.copytree(source / "site_content", tmp_path / "site_content")
    (tmp_path / "inputs").mkdir()
    shutil.copy(source / "inputs" / "companies.md", tmp_path / "inputs" / "companies.md")
    shutil.copy(
        source / "inputs" / "strategy-narratives.md",
        tmp_path / "inputs" / "strategy-narratives.md",
    )
    shutil.copy(
        source / "inputs" / "ethanol-strategy-prompt.md",
        tmp_path / "inputs" / "ethanol-strategy-prompt.md",
    )
    return load_config(tmp_path)
