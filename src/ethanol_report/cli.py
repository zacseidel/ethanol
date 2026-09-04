from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from .config import ConfigurationError, load_config


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ethanol-report")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="refresh data and create or replace a final report")
    run.add_argument("--date", type=parse_date, help="report date; defaults to today in America/Chicago")
    run.add_argument(
        "--report",
        choices=("ethanol",),
        default="ethanol",
        help="report scope to update (default: ethanol)",
    )
    run.add_argument(
        "--force-secondary",
        action="store_true",
        help="repeat earnings and narrative checks even if they already ran today",
    )
    render = subparsers.add_parser(
        "render", help="rebuild an existing report from saved data without network requests"
    )
    render.add_argument("--date", type=parse_date, required=True, help="published report date")
    render.add_argument(
        "--report", choices=("ethanol",), default="ethanol"
    )
    render.add_argument(
        "--refresh-charts",
        action="store_true",
        help="regenerate charts from the price cache instead of reusing published assets",
    )
    standalone = subparsers.add_parser(
        "export-standalone", help="create a self-contained HTML copy of an existing report"
    )
    standalone.add_argument("--date", type=parse_date, required=True, help="published report date")
    standalone.add_argument(
        "--report", choices=("ethanol",), default="ethanol"
    )
    standalone.add_argument("--output", type=Path, help="destination HTML path")
    site = subparsers.add_parser("build-site", help="build the static GitHub Pages website")
    site.add_argument("--output", type=Path, help="destination directory; defaults to docs/")
    subparsers.add_parser("validate", help="validate configuration without network requests")
    narrative = subparsers.add_parser(
        "refresh-narrative", help="refresh only the configured strategy narrative snapshot"
    )
    narrative.add_argument(
        "--report", choices=("ethanol",), default="ethanol"
    )
    strategy = subparsers.add_parser(
        "generate-strategy", help="generate a strategy brief with OpenAI"
    )
    strategy.add_argument("--date", type=parse_date, help="report date; defaults to today in America/Chicago")
    strategy.add_argument(
        "--report",
        choices=("ethanol", "farmer"),
        default="ethanol",
        help="strategy report profile (default: ethanol)",
    )
    strategy.add_argument(
        "--dry-run",
        action="store_true",
        help="assemble and print the request without calling OpenAI or writing reports",
    )
    strategy.add_argument(
        "--force",
        action="store_true",
        help="replace an existing strategy report for the same date",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config()
        try:
            from dotenv import load_dotenv

            load_dotenv(config.root / ".env", override=False)
        except ImportError:
            pass
        if args.command == "validate":
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "categories": len(config.universe.categories),
                        "companies": len(config.universe.companies),
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "generate-strategy":
            from .farmer import generate_farmer_brief
            from .narrative import refresh_narrative
            from .site import build_site
            from .strategy import generate_strategy_report

            config = config.for_scope("ethanol")
            report_date = args.date or datetime.now(config.timezone).date()
            if args.report == "farmer":
                result = generate_farmer_brief(
                    config,
                    report_date,
                    force=bool(args.force),
                    dry_run=bool(args.dry_run),
                )
                if not args.dry_run and result.get("content_markdown"):
                    build_site(config)
                print(json.dumps(result, indent=2))
                return 0
            config = config.for_scope(args.report)
            if args.dry_run:
                result = generate_strategy_report(config, report_date, dry_run=True)
            else:
                result = refresh_narrative(config, as_of=report_date, force=bool(args.force))
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "refresh-narrative":
            from .narrative import refresh_narrative

            config = config.for_scope(args.report)
            narrative = refresh_narrative(config)
            print(json.dumps(narrative, indent=2))
            return 0
        from .pipeline import export_standalone_report, rerender_report, run_report

        if args.command == "render":
            config = config.for_scope(args.report)
            result = rerender_report(
                config,
                args.date,
                refresh_charts=bool(args.refresh_charts),
            )
        elif args.command == "export-standalone":
            config = config.for_scope(args.report)
            result = export_standalone_report(config, args.date, args.output)
        elif args.command == "build-site":
            from .site import build_site

            result = build_site(config, args.output)
        else:
            report_date = args.date or datetime.now(config.timezone).date()
            scopes = (args.report,)
            results = []
            for scope in scopes:
                results.append(
                    run_report(
                        config.for_scope(scope),
                        report_date,
                        force_secondary=bool(args.force_secondary),
                    )
                )
            result = results[0] if len(results) == 1 else {"status": "ok", "reports": results}
        print(json.dumps(result, indent=2))
        return 0
    except (ConfigurationError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
