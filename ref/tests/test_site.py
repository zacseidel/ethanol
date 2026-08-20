from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from healthcare_report.site import _decorate_report, build_site


def _fake_report(
    root: Path,
    published: date,
    *,
    quality: str = "ok",
    report_type: str = "healthcare",
    headlines: tuple[tuple[str, str], ...] = (),
    earnings: tuple[tuple[str, str], ...] = (),
) -> None:
    relative = published.isoformat() if report_type == "healthcare" else f"{report_type}/{published.isoformat()}"
    folder = root / "reports" / "final" / relative
    assets = folder / "assets"
    assets.mkdir(parents=True)
    (assets / "chart.webp").write_bytes(b"RIFF-fake-webp")
    name = "Healthcare Intel" if report_type == "healthcare" else "Life Science and Device Intel"
    headline_links = "".join(
        f'<li><a href="#{fragment}">{label}</a></li>' for fragment, label in headlines
    )
    headline_sections = "".join(
        f'<h3 id="{fragment}">{label}</h3>' for fragment, label in headlines
    )
    earnings_links = "".join(
        f'<li><a href="#{fragment}">{label}</a></li>' for fragment, label in earnings
    )
    earnings_sections = "".join(
        f'<h3 id="{fragment}">{label}</h3>' for fragment, label in earnings
    )
    (folder / f"{name}-{published.isoformat()}.html").write_text(
        '<!doctype html><html><head><title>Weekly report</title></head><body>'
        f'<main><h1>Report for {published.isoformat()}</h1>'
        f'<nav class="strategy-narrative-links"><ul>{headline_links}</ul></nav>'
        f"{headline_sections}"
        f'<ul class="section-jump-list">{earnings_links}</ul>'
        f"{earnings_sections}"
        '<img src="assets/chart.webp" alt="Fixture chart"></main></body></html>',
        encoding="utf-8",
    )
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "report_date": published.isoformat(),
                "market_data_as_of": published.isoformat(),
                "quality": quality,
                "report_type": report_type,
                "report_name": name,
            }
        ),
        encoding="utf-8",
    )


def test_build_site_uses_latest_report_and_builds_public_pages(project):
    _fake_report(project.root, date(2026, 7, 27))
    _fake_report(project.root, date(2026, 8, 3), quality="degraded")

    output = project.root / "public-site"
    result = build_site(project, output)

    assert result == {
        "status": "ok",
        "output": str(output),
        "reports": 2,
        "latest_report": "2026-08-03",
    }
    home = BeautifulSoup((output / "index.html").read_text(), "html.parser")
    assert "Report for 2026-08-03" in home.get_text(" ", strip=True)
    assert len(home.select("header.public-site-header")) == 1
    assert len(home.select("nav.report-nav")) == 0
    assert home.select_one(".public-site-brand").get_text(strip=True) == "Weekly Intelligence"
    home_downloads = {
        link.get_text(strip=True): str(link["href"])
        for link in home.select(".report-downloads-page a")
    }
    assert home_downloads == {
        "PDF": "reports/2026-08-03/Healthcare%20Intel-2026-08-03.pdf",
        "HTML": "reports/2026-08-03/Healthcare%20Intel-2026-08-03.html",
    }
    assert home.select_one('nav.public-site-nav a[href="reports/"]') is not None
    assert home.select_one('nav.public-site-nav a[href="news/"]') is not None
    assert (output / "assets" / "chart.webp").is_file()
    assert "No published reports are available" not in (
        output / "news" / "index.html"
    ).read_text()

    archive = BeautifulSoup((output / "reports" / "index.html").read_text(), "html.parser")
    archive_links = [str(link["href"]) for link in archive.select(".report-list-link")]
    assert archive_links == ["2026-08-03/", "2026-07-27/"]
    assert len(archive.select(".report-list-actions .download-button")) == 4
    assert "Latest" in archive.get_text(" ", strip=True)
    assert "Data warning" not in archive.get_text(" ", strip=True)
    assert "Final" in archive.get_text(" ", strip=True)

    historical = BeautifulSoup(
        (output / "reports" / "2026-07-27" / "index.html").read_text(), "html.parser"
    )
    assert historical.select_one('nav.public-site-nav a[href="../../about/"]') is not None
    assert len(historical.select(".report-downloads-page .download-button")) == 2
    assert (output / "reports" / "2026-07-27" / "assets" / "chart.webp").is_file()
    assert (output / "reports" / "2026-08-03" / "Healthcare Intel-2026-08-03.html").is_file()
    assert (output / "reports" / "2026-08-03" / "Healthcare Intel-2026-08-03.pdf").read_bytes().startswith(b"%PDF")
    assert "About" in (output / "about" / "index.html").read_text()
    assert "Market performance" in (output / "methodology" / "index.html").read_text()
    assert (output / ".nojekyll").is_file()


def test_build_site_defaults_to_branch_publishable_docs_folder(project):
    _fake_report(project.root, date(2026, 8, 3))

    result = build_site(project)

    assert result["output"] == str(project.root / "docs")
    assert (project.root / "docs" / "index.html").is_file()


def test_news_and_earnings_index_has_an_empty_state_before_the_first_report(project):
    output = project.root / "public-site"
    build_site(project, output)

    index = BeautifulSoup((output / "news" / "index.html").read_text(), "html.parser")
    assert "No published reports are available to index" in index.get_text(" ", strip=True)
    assert index.select_one('nav.public-site-nav a[aria-current="page"]') is not None


def test_build_site_lists_both_report_types(project):
    _fake_report(project.root, date(2026, 8, 3))
    _fake_report(project.root, date(2026, 8, 3), report_type="life-science-device")

    output = project.root / "public-site"
    result = build_site(project, output)

    assert result["reports"] == 2
    archive = BeautifulSoup((output / "reports" / "index.html").read_text(), "html.parser")
    links = [str(link["href"]) for link in archive.select(".report-list-link")]
    assert links == ["2026-08-03/", "life-science-device/2026-08-03/"]
    assert "Life Sciences Intel Report" in archive.get_text(" ", strip=True)
    assert (output / "reports" / "life-science-device" / "2026-08-03" / "index.html").is_file()


def test_news_and_earnings_index_links_reports_by_week_and_business_topic(project):
    _fake_report(
        project.root,
        date(2026, 8, 10),
        headlines=(
            ("strategy-prior-auth", "Prior authorization accuracy becomes measurable"),
            ("strategy-epic-imaging", "Epic expands imaging interoperability"),
            ("strategy-rcm", "Revenue-cycle AI enters provider workflows"),
            ("strategy-payer", "Humana enrollment growth accelerates"),
            ("strategy-unclassified", "A new healthcare operating model emerges"),
        ),
        earnings=(("earnings-cah", "Cardinal Health (CAH)"),),
    )
    _fake_report(
        project.root,
        date(2026, 8, 10),
        report_type="life-science-device",
        headlines=(("strategy-fda-oncology", "FDA clears a new oncology therapy"),),
        earnings=(("earnings-lly", "Lilly (LLY)"),),
    )
    _fake_report(
        project.root,
        date(2026, 8, 3),
        headlines=(("strategy-no-surprises", "No Surprises Act ruling changes QPA economics"),),
    )

    output = project.root / "public-site"
    build_site(project, output)

    index = BeautifulSoup((output / "news" / "index.html").read_text(), "html.parser")
    week_labels = [heading.get_text(" ", strip=True) for heading in index.select(".index-week > h2")]
    assert week_labels == ["August 10, 2026", "August 3, 2026"]
    assert index.select_one(
        'a[href="../reports/2026-08-10/#strategy-prior-auth"]'
    ) is not None
    assert index.select_one(
        'a[href="../reports/life-science-device/2026-08-10/#earnings-lly"]'
    ) is not None
    assert len(index.select(".index-report-heading .download-button")) == 6
    assert index.select_one(
        'a[href="../reports/life-science-device/2026-08-10/'
        'Life%20Science%20and%20Device%20Intel-2026-08-10.pdf"]'
    ) is not None

    payment_integrity = index.select_one("#topic-payment-integrity")
    payer_strategy = index.select_one("#topic-payer-strategy")
    provider_strategy = index.select_one("#topic-provider-strategy")
    revenue_cycle = index.select_one("#topic-revenue-cycle-management")
    imaging = index.select_one("#topic-imaging")
    interoperability = index.select_one("#topic-edi-interoperability")
    life_sciences = index.select_one("#topic-life-sciences")
    policy = index.select_one("#topic-policy-cross-sector")
    other = index.select_one("#topic-other")
    assert payment_integrity is not None and "Prior authorization" in payment_integrity.get_text()
    assert payer_strategy is not None and "Humana enrollment" in payer_strategy.get_text()
    assert provider_strategy is not None and "provider workflows" in provider_strategy.get_text()
    assert revenue_cycle is not None and "Revenue-cycle AI" in revenue_cycle.get_text()
    assert imaging is not None and "Epic expands imaging" in imaging.get_text()
    assert interoperability is not None and "Epic expands imaging" in interoperability.get_text()
    assert life_sciences is not None and "new oncology therapy" in life_sciences.get_text()
    assert policy is not None and "FDA clears" in policy.get_text()
    assert other is not None and "operating model" in other.get_text()
    assert index.select_one('nav.public-site-nav a[aria-current="page"]') .get_text(
        " ", strip=True
    ) == "News & Earnings"


def test_decorating_already_decorated_report_does_not_nest_navigation(tmp_path):
    source = tmp_path / "source.html"
    destination = tmp_path / "published.html"
    source.write_text(
        "<!doctype html><html><head></head><body>"
        '<header class="public-site-header"></header>'
        '<div class="page-shell"><nav class="report-nav"></nav>'
        '<main><nav class="report-nav"></nav><h1>Report</h1></main></div>'
        "</body></html>",
        encoding="utf-8",
    )

    _decorate_report(source, destination, prefix="", active="latest")
    published = BeautifulSoup(destination.read_text(), "html.parser")
    assert len(published.select("header.public-site-header")) == 1
    assert len(published.select("nav.report-nav")) == 1


def test_homepage_remains_healthcare_when_life_science_is_newer(project):
    _fake_report(project.root, date(2026, 8, 3))
    _fake_report(project.root, date(2026, 8, 10), report_type="life-science-device")

    output = project.root / "public-site"
    build_site(project, output)

    home = BeautifulSoup((output / "index.html").read_text(), "html.parser")
    assert "Report for 2026-08-03" in home.get_text(" ", strip=True)
    archive = BeautifulSoup((output / "reports" / "index.html").read_text(), "html.parser")
    headings = [heading.get_text(" ", strip=True) for heading in archive.select(".report-group h2")]
    assert headings == ["Healthcare Intel Report", "Life Sciences Intel Report"]
