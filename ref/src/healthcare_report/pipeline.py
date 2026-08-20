from __future__ import annotations

import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .analysis import (
    CHANGE_FIELDS,
    SNAPSHOT_FIELDS,
    Baseline,
    build_snapshot,
    compare_snapshots,
    data_issues,
    find_baseline,
    load_snapshot,
    months_before,
    notable_change_summary,
    period_moves,
)
from .cache import MarketCache
from .config import ProjectConfig
from .earnings import (
    load_earnings_state,
    refresh_earnings,
    refresh_needed,
    save_earnings_state,
)
from .narrative import (
    load_narrative,
    narrative_age,
    refresh_narrative_with_fallback,
)
from .providers import BrowserSession, FetchStatus, MassiveClient
from .render import (
    build_markdown,
    render_charts,
    render_earnings_charts,
    report_html_name,
    select_chart_tickers,
    standalone_html_name,
    write_report_files,
    write_standalone_report,
)
from .storage import (
    atomic_replace_directory,
    config_hash,
    read_gzip_json,
    read_json,
    utc_now,
    write_csv,
    write_gzip_json,
    write_json,
)
from .strategy import strategy_prompt_path


def _status(source: str, subject: str, status: str, detail: str = "") -> FetchStatus:
    return FetchStatus(source, subject, status, detail)


def _progress(message: str) -> None:
    print(f"[report] {message}", file=sys.stderr, flush=True)


def _provider_result(provider: Any) -> tuple[str, str]:
    return str(getattr(provider, "last_status", "ok")), str(getattr(provider, "last_detail", ""))


def _round_seconds(value: float) -> float:
    return round(value, 3)


def _asset_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _report_windows(config: ProjectConfig, report_date: date) -> tuple[date, date, int]:
    longest = max(
        [int(item) for item in config.settings["report"]["return_horizons_months"]]
        + [int(item) for item in config.settings["report"]["chart_horizons_months"]]
    )
    return (
        months_before(report_date, longest) - timedelta(days=14),
        report_date - timedelta(days=1),
        longest,
    )


def _earnings_sections(
    config: ProjectConfig,
    earnings: dict[str, dict[str, Any]],
    report_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    window = int(config.settings["earnings"].get("window_days", 7))
    recent: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    for ticker, company in config.universe.companies.items():
        record = earnings.get(ticker, {})
        try:
            last = (
                date.fromisoformat(str(record["last_report_date"]))
                if record.get("last_report_date")
                else None
            )
        except ValueError:
            last = None
        try:
            event = (
                date.fromisoformat(str(record["next_event_date"]))
                if record.get("next_event_date")
                else None
            )
        except ValueError:
            event = None
        if last and report_date - timedelta(days=window) <= last <= report_date:
            recent.append({"ticker": ticker, "name": company.name, **record})
        if event and report_date <= event <= report_date + timedelta(days=window):
            upcoming.append(
                {
                    "ticker": ticker,
                    "name": company.name,
                    "date": event.isoformat(),
                    "status": record.get("next_date_status") or "unknown",
                    "source": record.get("next_date_source") or "unknown",
                }
            )
    upcoming.sort(key=lambda row: (row["date"], row["ticker"]))
    return recent, upcoming


def _file_size_summary(folder: Path, files: list[str]) -> dict[str, int]:
    sizes = {
        relative: (folder / relative).stat().st_size
        for relative in files
        if (folder / relative).is_file()
    }
    chart_bytes = sum(size for name, size in sizes.items() if name.startswith("assets/"))
    data_bytes = sum(
        size
        for name, size in sizes.items()
        if name in {"snapshot.csv", "changes.csv", "render-data.json.gz"}
    )
    return {
        "html": sizes.get(next((name for name in sizes if name.endswith(".html")), ""), 0),
        "markdown": sizes.get("report.md", 0),
        "charts": chart_bytes,
        "data": data_bytes,
        "total_without_manifest": sum(sizes.values()),
    }


def _render_final(
    config: ProjectConfig,
    report_date: date,
    market_data_as_of: date,
    snapshot: list[dict[str, Any]],
    baseline: Baseline | None,
    changes: list[dict[str, Any]],
    bars: dict[str, list[dict[str, Any]]],
    reference: dict[str, dict[str, Any]],
    earnings: dict[str, dict[str, Any]],
    narrative: dict[str, Any] | None,
    status_rows: list[dict[str, str]],
    issues: list[str],
    stage_durations: dict[str, float],
    *,
    generated_at: str | None = None,
    mode: str = "full",
    recent: list[dict[str, Any]] | None = None,
    upcoming: list[dict[str, Any]] | None = None,
    moves: dict[str, Any] | None = None,
    reuse_assets_from: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    render_started = time.perf_counter()
    final_root = config.final_root
    final_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{report_date.isoformat()}-", dir=final_root))
    try:
        if recent is None or upcoming is None:
            recent, upcoming = _earnings_sections(config, earnings, report_date)
        if moves is None:
            moves = period_moves(config, bars, reference, baseline, report_date)
        notable_summary = notable_change_summary(changes, config)
        chart_tickers = select_chart_tickers(snapshot, config)
        earnings_chart_tickers = [
            item["ticker"]
            for item in recent
            if item.get("summary") or item.get("at_a_glance") or item.get("key_moments")
        ]
        overview_chart_tickers = [
            ticker for ticker in config.universe.companies if ticker not in earnings_chart_tickers
        ]
        charts: list[tuple[int, Path]] = []
        earnings_charts: dict[str, Path] = {}
        overview_charts: dict[str, Path] = {}
        if reuse_assets_from is not None:
            assets = temporary / "assets"
            assets.mkdir(parents=True, exist_ok=True)
            for horizon in config.settings["report"]["chart_horizons_months"]:
                source = reuse_assets_from / "assets" / f"performance-{horizon}m.webp"
                if source.is_file():
                    destination = assets / source.name
                    shutil.copy2(source, destination)
                    charts.append((int(horizon), destination))
            for ticker in earnings_chart_tickers:
                source = reuse_assets_from / "assets" / f"earnings-{_asset_slug(ticker)}-3m.webp"
                if source.is_file():
                    destination = assets / source.name
                    shutil.copy2(source, destination)
                    earnings_charts[ticker] = destination
            for ticker in overview_chart_tickers:
                source = reuse_assets_from / "assets" / f"earnings-{_asset_slug(ticker)}-3m.webp"
                if source.is_file():
                    destination = assets / source.name
                    shutil.copy2(source, destination)
                    overview_charts[ticker] = destination
        expected_horizons = {
            int(item) for item in config.settings["report"]["chart_horizons_months"]
        }
        if {horizon for horizon, _path in charts} != expected_horizons:
            for _horizon, path in charts:
                path.unlink(missing_ok=True)
            charts = render_charts(temporary, config, report_date, bars, chart_tickers)
        missing_earnings = [
            ticker for ticker in earnings_chart_tickers if ticker not in earnings_charts
        ]
        if missing_earnings:
            earnings_charts.update(
                render_earnings_charts(temporary, config, report_date, bars, missing_earnings)
            )
        missing_overview = [
            ticker for ticker in overview_chart_tickers if ticker not in overview_charts
        ]
        if missing_overview and any(bars.values()):
            overview_charts.update(
                render_earnings_charts(temporary, config, report_date, bars, missing_overview)
            )
        context = {
            "config": config,
            "report_date": report_date,
            "market_data_as_of": market_data_as_of,
            "snapshot": snapshot,
            "baseline": baseline,
            "changes": changes,
            "notable": notable_summary["items"],
            "notable_summary": notable_summary,
            "overview_charts": overview_charts,
            "period_moves": moves,
            "charts": charts,
            "earnings_charts": earnings_charts,
            "earnings": earnings,
            "upcoming_earnings": upcoming,
            "recent_earnings": recent,
            "narrative": narrative,
            "reference": reference,
            "statuses": status_rows,
            "issues": issues,
        }
        markdown_text = build_markdown(context)
        html_name = report_html_name(report_date, config)
        write_report_files(temporary, markdown_text, report_date, config)
        write_csv(temporary / "snapshot.csv", snapshot, SNAPSHOT_FIELDS)
        write_csv(temporary / "changes.csv", changes, CHANGE_FIELDS)
        write_gzip_json(
            temporary / "render-data.json.gz",
            {
                "schema": 1,
                "reference": reference,
                "recent_earnings": recent,
                "upcoming_earnings": upcoming,
                "narrative": narrative,
                "period_moves": moves,
            },
        )
        files = [
            html_name,
            "report.md",
            "snapshot.csv",
            "changes.csv",
            "render-data.json.gz",
            *[f"assets/{path.name}" for _, path in charts],
            *[f"assets/{path.name}" for path in earnings_charts.values()],
            *[f"assets/{path.name}" for path in overview_charts.values()],
        ]
        durations = {key: _round_seconds(value) for key, value in stage_durations.items()}
        durations["rendering"] = _round_seconds(time.perf_counter() - render_started)
        manifest = {
            "schema": 2,
            "report_type": config.scope,
            "report_name": config.report_name,
            "report_date": report_date.isoformat(),
            "market_data_as_of": market_data_as_of.isoformat(),
            "generated_at": generated_at or utc_now(),
            "rendered_at": utc_now(),
            "baseline_report_date": baseline.report_date.isoformat() if baseline else None,
            "configuration_sha256": config_hash(
                [
                    config.root / "config" / "settings.yaml",
                    config.root / "inputs" / "companies.md",
                    strategy_prompt_path(config),
                ]
            ),
            "quality": "degraded" if issues else "ok",
            "issues": issues,
            "sources": status_rows,
            "metrics": {
                "mode": mode,
                "durations_seconds": durations,
                "counts": {
                    "companies": len(config.universe.companies),
                    "price_bars_loaded": sum(len(rows) for rows in bars.values()),
                    "performance_charts": len(charts),
                    "earnings_charts": len(earnings_charts),
                    "source_statuses": dict(Counter(row["status"] for row in status_rows)),
                },
                "output_bytes": _file_size_summary(temporary, files),
            },
            "files": files,
        }
        write_json(temporary / "manifest.json", manifest)
        for required in (
            html_name,
            "report.md",
            "snapshot.csv",
            "changes.csv",
            "render-data.json.gz",
            "manifest.json",
        ):
            if not (temporary / required).exists() or not (temporary / required).stat().st_size:
                raise RuntimeError(f"report validation failed: {required} is missing or empty")
        destination = final_root / report_date.isoformat()
        atomic_replace_directory(temporary, destination)
        return destination, manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def _finish_manifest(
    destination: Path,
    *,
    total_seconds: float,
    retention: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = destination / "manifest.json"
    manifest = read_json(path, {})
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Cannot update invalid manifest: {path}")
    metrics = manifest.setdefault("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
        manifest["metrics"] = metrics
    durations = metrics.setdefault("durations_seconds", {})
    if isinstance(durations, dict):
        durations["total"] = _round_seconds(total_seconds)
    if retention is not None:
        metrics["price_retention"] = retention
    metrics["directory_bytes"] = sum(
        item.stat().st_size for item in destination.rglob("*") if item.is_file()
    )
    write_json(path, manifest)
    return manifest


def run_report(
    config: ProjectConfig,
    report_date: date,
    *,
    force_secondary: bool = False,
) -> dict[str, Any]:
    total_started = time.perf_counter()
    _progress(
        f"Starting final report for {report_date.isoformat()}. "
        "Massive requests are rate-limited, so this can take several minutes."
    )
    statuses: list[FetchStatus] = []
    tickers = list(config.universe.companies)
    benchmark = str(config.settings["report"].get("benchmark", "SPY"))
    price_start, price_end, longest = _report_windows(config, report_date)
    reference: dict[str, dict[str, Any]] = {}
    bars: dict[str, list[dict[str, Any]]] = {}
    stage_durations: dict[str, float] = {}
    market_started = time.perf_counter()
    massive = MassiveClient(config)
    try:
        market_total = len(tickers) + 1
        grouped_update = getattr(massive, "prefetch_grouped_prices", None)
        if callable(grouped_update):
            grouped_update([*tickers, benchmark], price_start, price_end, progress=_progress)
        for index, ticker in enumerate(tickers, start=1):
            try:
                _progress(f"Market {index}/{market_total}: loading {ticker} company profile...")
                reference[ticker] = massive.company(ticker)
                provider_status, detail = _provider_result(massive)
                statuses.append(_status("Massive company", ticker, provider_status, detail))
                _progress(
                    f"Market {index}/{market_total}: {ticker} profile — {detail or 'complete'}."
                )
            except Exception as exc:
                statuses.append(_status("Massive company", ticker, "warning", str(exc)))
            try:
                _progress(f"Market {index}/{market_total}: loading {ticker} price history...")
                bars[ticker] = massive.prices(ticker, price_start, price_end)
                provider_status, detail = _provider_result(massive)
                status = provider_status if bars[ticker] else "failed"
                statuses.append(
                    _status(
                        "Massive prices",
                        ticker,
                        status,
                        detail if bars[ticker] else "no bars returned",
                    )
                )
                _progress(
                    f"Market {index}/{market_total}: {ticker} prices — {detail or 'complete'}."
                )
            except Exception as exc:
                bars[ticker] = []
                statuses.append(_status("Massive prices", ticker, "failed", str(exc)))
        try:
            _progress(
                f"Market {market_total}/{market_total}: loading {benchmark} benchmark history..."
            )
            bars[benchmark] = massive.prices(benchmark, price_start, price_end)
            provider_status, detail = _provider_result(massive)
            statuses.append(
                _status(
                    "Massive prices",
                    benchmark,
                    provider_status if bars[benchmark] else "warning",
                    detail,
                )
            )
            _progress(
                f"Market {market_total}/{market_total}: {benchmark} prices — {detail or 'complete'}."
            )
        except Exception as exc:
            bars[benchmark] = []
            statuses.append(_status("Massive prices", benchmark, "warning", str(exc)))
        stage_durations["market_data"] = time.perf_counter() - market_started

        analysis_started = time.perf_counter()
        _progress("Calculating returns, ranks, and changes from the previous report...")
        snapshot, market_data_as_of = build_snapshot(config, report_date, bars, reference)
        baseline = find_baseline(config, report_date)
        changes = compare_snapshots(snapshot, baseline, config)
        stage_durations["analysis"] = time.perf_counter() - analysis_started

        secondary_started = time.perf_counter()
        checked_on = datetime.now(UTC).date()
        earnings_state = load_earnings_state(config)
        earnings_due = force_secondary or any(
            refresh_needed(earnings_state.get(ticker), report_date, config, checked_on=checked_on)
            for ticker in tickers
        )
        browser: BrowserSession | None = None
        browser_needed = earnings_due
        if browser_needed:
            try:
                _progress("Starting the secondary-source browser...")
                browser = BrowserSession()
                browser.__enter__()
                statuses.append(_status("browser", "Chromium", "ok"))
            except Exception as exc:
                browser = None
                statuses.append(_status("browser", "Chromium", "warning", str(exc)))
        else:
            statuses.append(_status("browser", "Chromium", "skipped", "no refresh was due"))
        try:
            earnings, earnings_status = refresh_earnings(
                config,
                report_date,
                reference,
                browser,
                progress=_progress,
                state=earnings_state,
                checked_on=checked_on,
                force=force_secondary,
            )
            statuses.extend(earnings_status)
            narrative_provider = "OpenAI Responses API"
            _progress(f"Refreshing the strategy narrative via {narrative_provider}...")
            narrative, narrative_status, narrative_detail = refresh_narrative_with_fallback(
                config,
                browser,
                as_of=report_date,
                checked_on=checked_on,
                force=force_secondary,
            )
            statuses.append(
                _status(
                    "strategy narrative",
                    narrative_provider,
                    narrative_status,
                    narrative_detail,
                )
            )
        finally:
            if browser is not None:
                browser.__exit__(None, None, None)
        stage_durations["secondary_sources"] = time.perf_counter() - secondary_started
    finally:
        massive.close()

    status_rows = [item.as_dict() for item in statuses]
    issues = data_issues(config, snapshot, status_rows, narrative_age(narrative, report_date))
    _progress("Rendering charts and final report files...")
    destination, _manifest = _render_final(
        config,
        report_date,
        market_data_as_of,
        snapshot,
        baseline,
        changes,
        bars,
        reference,
        earnings,
        narrative,
        status_rows,
        issues,
        stage_durations,
    )
    save_earnings_state(config, earnings)
    retention: dict[str, Any]
    try:
        buffer_days = int(config.settings["market_data"].get("price_retention_buffer_days", 45))
        cutoff = months_before(report_date, longest) - timedelta(days=buffer_days)
        retention = MarketCache(config).prune_prices([*tickers, benchmark], cutoff)
    except Exception as exc:
        retention = {"status": "warning", "detail": str(exc)}
        _progress(f"Price-cache retention warning: {exc}")
    manifest = _finish_manifest(
        destination,
        total_seconds=time.perf_counter() - total_started,
        retention=retention,
    )
    from .site import build_site

    site = build_site(config)
    html_name = report_html_name(report_date, config)
    _progress(f"Complete: {destination.relative_to(config.root)}/{html_name}")
    _progress("Public site rebuilt: docs/index.html")
    return {
        "status": manifest["quality"],
        "report_date": report_date.isoformat(),
        "market_data_as_of": market_data_as_of.isoformat(),
        "report_type": config.scope,
        "output": str((destination / html_name).relative_to(config.root)),
        "site_output": str(Path(site["output"]).relative_to(config.root)),
        "baseline": baseline.report_date.isoformat() if baseline else None,
        "issues": issues,
        "metrics": manifest.get("metrics", {}),
    }


def rerender_report(
    config: ProjectConfig,
    report_date: date,
    *,
    refresh_charts: bool = False,
) -> dict[str, Any]:
    total_started = time.perf_counter()
    folder = config.report_folder(report_date)
    manifest = read_json(folder / "manifest.json", {})
    if not isinstance(manifest, dict) or not manifest.get("report_date"):
        raise RuntimeError(f"No published report is available for {report_date.isoformat()}")
    snapshot = load_snapshot(folder / "snapshot.csv")
    if not snapshot:
        raise RuntimeError(f"Cannot rerender {report_date.isoformat()}; snapshot.csv is empty")
    load_started = time.perf_counter()
    price_start, price_end, _longest = _report_windows(config, report_date)
    benchmark = str(config.settings["report"].get("benchmark", "SPY"))
    cache = MarketCache(config)
    render_data = read_gzip_json(folder / "render-data.json.gz", {})
    if not isinstance(render_data, dict):
        render_data = {}
    reference_value = render_data.get("reference") or cache.reference()
    reference = (
        {
            str(ticker): dict(record)
            for ticker, record in reference_value.items()
            if isinstance(record, dict)
        }
        if isinstance(reference_value, dict)
        else cache.reference()
    )
    # A normal rerender reuses the already-published chart assets and the saved
    # period-move data. Avoid reopening the provider cache unless charts were
    # explicitly requested for refresh; this keeps presentation-only rebuilds
    # independent of unrelated cache files.
    bars = (
        {
            ticker: cache.price_bars(ticker, price_start, price_end)
            for ticker in [*config.universe.companies, benchmark]
        }
        if refresh_charts
        else {}
    )
    baseline = find_baseline(config, report_date)
    changes = compare_snapshots(snapshot, baseline, config)
    # The published render data already contains the earnings sections needed
    # for a presentation-only rebuild; do not reopen the mutable earnings
    # cache unless a full report update is being run.
    earnings: dict[str, dict[str, Any]] = {}
    narrative_value = render_data.get("narrative")
    narrative = narrative_value if isinstance(narrative_value, dict) else load_narrative(config)
    recent_value = render_data.get("recent_earnings")
    upcoming_value = render_data.get("upcoming_earnings")
    recent = (
        [dict(row) for row in recent_value if isinstance(row, dict)]
        if isinstance(recent_value, list)
        else None
    )
    upcoming = (
        [dict(row) for row in upcoming_value if isinstance(row, dict)]
        if isinstance(upcoming_value, list)
        else None
    )
    moves_value = render_data.get("period_moves")
    moves = dict(moves_value) if isinstance(moves_value, dict) else None
    status_rows = [dict(row) for row in manifest.get("sources", []) if isinstance(row, dict)]
    issues = data_issues(config, snapshot, status_rows, narrative_age(narrative, report_date))
    destination, _new_manifest = _render_final(
        config,
        report_date,
        snapshot[0]["market_data_as_of"],
        snapshot,
        baseline,
        changes,
        bars,
        reference,
        earnings,
        narrative,
        status_rows,
        issues,
        {"render_input_load": time.perf_counter() - load_started},
        generated_at=str(manifest.get("generated_at") or utc_now()),
        mode="render-only",
        recent=recent,
        upcoming=upcoming,
        moves=moves,
        reuse_assets_from=None if refresh_charts else folder,
    )
    final_manifest = _finish_manifest(
        destination,
        total_seconds=time.perf_counter() - total_started,
    )
    from .site import build_site

    site = build_site(config)
    html_name = report_html_name(report_date, config)
    return {
        "status": final_manifest["quality"],
        "report_date": report_date.isoformat(),
        "market_data_as_of": snapshot[0]["market_data_as_of"].isoformat(),
        "output": str((destination / html_name).relative_to(config.root)),
        "site_output": str(Path(site["output"]).relative_to(config.root)),
        "mode": "render-only",
        "issues": issues,
        "metrics": final_manifest.get("metrics", {}),
    }


def export_standalone_report(
    config: ProjectConfig,
    report_date: date,
    output: Path | None = None,
) -> dict[str, Any]:
    folder = config.report_folder(report_date)
    if not folder.is_dir():
        raise RuntimeError(f"No published report is available for {report_date.isoformat()}")
    destination = output or (
        config.root / "reports" / "standalone" / standalone_html_name(report_date, config)
    )
    path = write_standalone_report(folder, report_date, destination.resolve())
    return {
        "status": "ok",
        "report_date": report_date.isoformat(),
        "output": str(path),
        "bytes": path.stat().st_size,
    }
