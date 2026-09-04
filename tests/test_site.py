from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from ethanol_report.site import _decorate_report, build_site


def _fake_report(
    root: Path,
    published: date,
    *,
    quality: str = "ok",
    report_type: str = "ethanol",
    headlines: tuple[tuple[str, str], ...] = (),
    earnings: tuple[tuple[str, str], ...] = (),
) -> None:
    relative = published.isoformat() if report_type == "ethanol" else f"{report_type}/{published.isoformat()}"
    folder = root / "reports" / "final" / relative
    assets = folder / "assets"
    assets.mkdir(parents=True)
    (assets / "chart.webp").write_bytes(b"RIFF-fake-webp")
    name = {
        "ethanol": "Weekly Corn and Ethanol Intel Report",
        "farmer": "Farmer Corn Brief",
    }.get(report_type, report_type)
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
    assert home.select_one(".public-site-brand").get_text(strip=True) == "Ethanol Strategy Digest"
    home_downloads = {
        link.get_text(strip=True): str(link["href"])
        for link in home.select(".report-downloads-page a")
    }
    assert home_downloads == {
        "PDF": "reports/2026-08-03/Weekly%20Corn%20and%20Ethanol%20Intel%20Report-2026-08-03.pdf",
        "HTML": "reports/2026-08-03/Weekly%20Corn%20and%20Ethanol%20Intel%20Report-2026-08-03.html",
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
    assert (
        output / "reports" / "2026-08-03" / "Weekly Corn and Ethanol Intel Report-2026-08-03.html"
    ).is_file()
    assert (
        output / "reports" / "2026-08-03" / "Weekly Corn and Ethanol Intel Report-2026-08-03.pdf"
    ).read_bytes().startswith(b"%PDF")
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


def test_build_site_lists_ethanol_reports_only(project):
    _fake_report(project.root, date(2026, 8, 3))
    _fake_report(project.root, date(2026, 7, 27))

    output = project.root / "public-site"
    result = build_site(project, output)

    assert result["reports"] == 2
    archive = BeautifulSoup((output / "reports" / "index.html").read_text(), "html.parser")
    links = [str(link["href"]) for link in archive.select(".report-list-link")]
    assert links == ["2026-08-03/", "2026-07-27/"]
    assert "Weekly Corn and Ethanol Intel Report" in archive.get_text(" ", strip=True)
    assert "Farmer Corn Brief" in archive.get_text(" ", strip=True)
    assert (output / "reports" / "2026-08-03" / "index.html").is_file()


def test_build_site_lists_farmer_briefs_separately_and_uses_farmer_homepage(project):
    _fake_report(
        project.root,
        date(2026, 8, 3),
        headlines=(("strategy-crush", "Midwest crush margins compress on higher corn"),),
        earnings=(("earnings-gpre", "Green Plains (GPRE)"),),
    )
    _fake_report(
        project.root,
        date(2026, 8, 3),
        report_type="farmer",
        headlines=(("strategy-rally", "The board paid you this week"),),
    )
    _fake_report(project.root, date(2026, 7, 27), report_type="farmer")

    output = project.root / "public-site"
    result = build_site(project, output)

    assert result["reports"] == 3
    assert result["latest_report"] == "2026-08-03"
    home = BeautifulSoup((output / "index.html").read_text(), "html.parser")
    assert "Report for 2026-08-03" in home.get_text(" ", strip=True)
    assert "The board paid you this week" in home.get_text(" ", strip=True)
    assert "Midwest crush margins compress on higher corn" not in home.get_text(" ", strip=True)
    home_downloads = {
        link.get_text(strip=True): str(link["href"])
        for link in home.select(".report-downloads-page a")
    }
    assert home_downloads == {
        "PDF": "reports/farmer/2026-08-03/Farmer%20Corn%20Brief-2026-08-03.pdf",
        "HTML": "reports/farmer/2026-08-03/Farmer%20Corn%20Brief-2026-08-03.html",
    }

    archive = BeautifulSoup((output / "reports" / "index.html").read_text(), "html.parser")
    headings = [heading.get_text(strip=True) for heading in archive.select(".report-group h2")]
    assert headings == ["Weekly Corn and Ethanol Intel Report", "Farmer Corn Brief"]
    links = [str(link["href"]) for link in archive.select(".report-list-link")]
    assert "2026-08-03/" in links
    assert "farmer/2026-08-03/" in links
    assert "farmer/2026-07-27/" in links
    assert "Nearby corn through" in archive.get_text(" ", strip=True)
    assert (output / "reports" / "farmer" / "2026-08-03" / "index.html").is_file()

    news = BeautifulSoup((output / "news" / "index.html").read_text(), "html.parser")
    assert "Midwest crush margins" in news.get_text(" ", strip=True)
    assert "The board paid you this week" not in news.get_text(" ", strip=True)
    assert "July 27, 2026" not in news.get_text(" ", strip=True)
    assert news.select_one('a[href="../reports/farmer/2026-08-03/"]') is None


def test_news_and_earnings_index_links_reports_by_week_and_business_topic(project):
    _fake_report(
        project.root,
        date(2026, 8, 10),
        headlines=(
            ("strategy-crush", "Midwest crush margins compress on higher corn"),
            ("strategy-rfs", "EPA posts a new RVO proposal"),
            ("strategy-rail", "Union Pacific slows ethanol tank-car cycle times"),
            ("strategy-gpre", "Green Plains earnings highlight corn-oil strength"),
            ("strategy-unclassified", "A new operating model emerges"),
        ),
        earnings=(("earnings-gpre", "Green Plains (GPRE)"),),
    )
    _fake_report(
        project.root,
        date(2026, 8, 3),
        headlines=(("strategy-wasde", "WASDE lifts corn yield and ending stocks"),),
    )

    output = project.root / "public-site"
    build_site(project, output)

    index = BeautifulSoup((output / "news" / "index.html").read_text(), "html.parser")
    week_labels = [heading.get_text(" ", strip=True) for heading in index.select(".index-week > h2")]
    assert week_labels == ["August 10, 2026", "August 3, 2026"]
    assert index.select_one(
        'a[href="../reports/2026-08-10/#strategy-crush"]'
    ) is not None
    assert index.select_one(
        'a[href="../reports/2026-08-10/#earnings-gpre"]'
    ) is not None
    assert len(index.select(".index-report-heading .download-button")) == 4

    crush = index.select_one("#topic-crush-margins")
    corn = index.select_one("#topic-corn-feedstocks")
    rfs = index.select_one("#topic-rfs")
    rail = index.select_one("#topic-logistics-rail")
    earnings = index.select_one("#topic-earnings")
    other = index.select_one("#topic-other")
    assert crush is not None and "crush margins" in crush.get_text()
    assert corn is not None and "WASDE" in corn.get_text()
    assert rfs is not None and "RVO" in rfs.get_text()
    assert rail is not None and "Union Pacific" in rail.get_text()
    assert earnings is not None and "Green Plains earnings" in earnings.get_text()
    assert other is not None and "operating model" in other.get_text()
    assert index.select_one('nav.public-site-nav a[aria-current="page"]').get_text(
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


def test_homepage_uses_the_newest_farmer_brief_even_if_ethanol_is_newer(project):
    _fake_report(project.root, date(2026, 8, 10))
    _fake_report(project.root, date(2026, 8, 3), report_type="farmer")
    _fake_report(project.root, date(2026, 7, 27), report_type="farmer")

    output = project.root / "public-site"
    result = build_site(project, output)

    assert result["latest_report"] == "2026-08-03"
    home = BeautifulSoup((output / "index.html").read_text(), "html.parser")
    assert "Report for 2026-08-03" in home.get_text(" ", strip=True)
    assert "Report for 2026-08-10" not in home.get_text(" ", strip=True)
    archive = BeautifulSoup((output / "reports" / "index.html").read_text(), "html.parser")
    headings = [heading.get_text(" ", strip=True) for heading in archive.select(".report-group h2")]
    assert headings == ["Weekly Corn and Ethanol Intel Report", "Farmer Corn Brief"]
