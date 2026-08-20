from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


class ConfigurationError(ValueError):
    """Raised when a human-editable project configuration is invalid."""


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    description: str


@dataclass(frozen=True)
class Universe:
    categories: dict[str, tuple[Company, ...]]

    @property
    def companies(self) -> dict[str, Company]:
        result: dict[str, Company] = {}
        for members in self.categories.values():
            for company in members:
                existing = result.get(company.ticker)
                if existing and existing != company:
                    raise ConfigurationError(
                        f"{company.ticker} has conflicting names or descriptions across categories"
                    )
                result[company.ticker] = company
        return result

    @property
    def memberships(self) -> list[tuple[str, Company]]:
        return [
            (category, company)
            for category, members in self.categories.items()
            for company in members
        ]


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    settings: dict[str, Any]
    universe: Universe
    scope: str = "ethanol"
    available_universe: Universe | None = None

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.settings["report"]["timezone"])

    @property
    def report_slug(self) -> str:
        return str(self.settings["report"].get("slug") or self.scope)

    @property
    def report_name(self) -> str:
        return str(self.settings["report"]["name"])

    @property
    def final_root(self) -> Path:
        root = self.root / "reports" / "final"
        default = str(self.settings.get("report", {}).get("slug") or self.scope)
        return root if self.scope == default else root / self.report_slug

    def report_folder(self, report_date: Any) -> Path:
        return self.final_root / str(report_date)

    def for_scope(self, scope: str) -> ProjectConfig:
        profiles = self.settings.get("report_profiles", {})
        profile = profiles.get(scope)
        if not isinstance(profile, dict):
            raise ConfigurationError(f"Unknown report scope: {scope}")
        source_universe = self.available_universe or self.universe
        categories = profile.get("categories")
        if not isinstance(categories, list) or not categories:
            raise ConfigurationError(f"report profile {scope} must list categories")
        missing = [category for category in categories if category not in source_universe.categories]
        if missing:
            raise ConfigurationError(
                f"report profile {scope} references unknown categories: {', '.join(missing)}"
            )
        settings = deepcopy(self.settings)
        report = dict(settings["report"])
        report.update({key: value for key, value in profile.items() if key != "categories"})
        report["slug"] = scope
        settings["report"] = report
        narrative = profile.get("strategy_narrative")
        if not isinstance(narrative, dict):
            raise ConfigurationError(f"report profile {scope} must define strategy_narrative")
        settings["strategy_narrative"] = deepcopy(narrative)
        selected = {category: source_universe.categories[category] for category in categories}
        return ProjectConfig(self.root, settings, Universe(selected), scope, source_universe)


def project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "config").is_dir():
            return candidate
    raise ConfigurationError("Cannot locate the project root containing pyproject.toml and config/")


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Missing configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{path} must contain a YAML mapping")
    return value


def _read_markdown_frontmatter(path: Path) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Missing configuration file: {path}") from exc
    if not lines or lines[0].strip() != "---":
        raise ConfigurationError(f"{path} must begin with a YAML front matter delimiter (---)")
    try:
        closing = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise ConfigurationError(f"{path} is missing its closing YAML delimiter (---)") from exc
    try:
        value = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{path} front matter must contain category mappings")
    return value


def _require_mapping(settings: dict[str, Any], name: str) -> dict[str, Any]:
    value = settings.get(name)
    if not isinstance(value, dict):
        raise ConfigurationError(f"settings.{name} must be a mapping")
    return value


def _validate_settings(settings: dict[str, Any]) -> None:
    for section in (
        "report",
        "market_data",
        "earnings",
        "notable_changes",
        "strategy_narrative",
    ):
        _require_mapping(settings, section)
    report = settings["report"]
    for key in ("name", "timezone", "benchmark"):
        if not str(report.get(key, "")).strip():
            raise ConfigurationError(f"settings.report.{key} is required")
    try:
        ZoneInfo(str(report["timezone"]))
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(f"Unknown timezone: {report['timezone']}") from exc
    horizons = report.get("return_horizons_months")
    if not isinstance(horizons, list) or not horizons or any(int(item) <= 0 for item in horizons):
        raise ConfigurationError("settings.report.return_horizons_months must be positive integers")
    market_data = settings["market_data"]
    if int(market_data.get("company_cache_days", 90)) <= 0:
        raise ConfigurationError("settings.market_data.company_cache_days must be positive")
    if int(market_data.get("price_retention_buffer_days", 45)) < 14:
        raise ConfigurationError(
            "settings.market_data.price_retention_buffer_days must be at least 14"
        )
    earnings = settings["earnings"]
    interval = int(earnings.get("tentative_interval_days", 90))
    lead = int(earnings.get("tentative_check_lead_days", 21))
    if interval <= lead or lead < 0:
        raise ConfigurationError("earnings tentative interval must be greater than its check lead")
    profiles = settings.get("report_profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ConfigurationError("settings.report_profiles must define at least one profile")
    for scope, profile in profiles.items():
        if not isinstance(profile, dict):
            raise ConfigurationError(f"settings.report_profiles.{scope} must be a mapping")
        if not str(profile.get("name") or "").strip():
            raise ConfigurationError(f"settings.report_profiles.{scope}.name is required")
        categories = profile.get("categories")
        if not isinstance(categories, list) or not categories:
            raise ConfigurationError(f"settings.report_profiles.{scope}.categories is required")
        narrative = profile.get("strategy_narrative")
        if not isinstance(narrative, dict):
            raise ConfigurationError(
                f"settings.report_profiles.{scope}.strategy_narrative is required"
            )


def _load_universe(document: dict[str, Any]) -> Universe:
    raw_categories = document
    if not raw_categories:
        raise ConfigurationError("inputs/companies.md must define at least one category")
    categories: dict[str, tuple[Company, ...]] = {}
    ticker_pattern = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
    for raw_name, raw_members in raw_categories.items():
        name = str(raw_name).strip()
        if not name or not isinstance(raw_members, dict) or not raw_members:
            raise ConfigurationError(f"Category {raw_name!r} must contain at least one company")
        members: list[Company] = []
        for raw_ticker, raw_details in raw_members.items():
            ticker = str(raw_ticker).strip().upper()
            details = str(raw_details).strip()
            company_name, separator, description = details.partition(";")
            company_name = company_name.strip()
            description = description.strip()
            if not ticker_pattern.fullmatch(ticker):
                raise ConfigurationError(f"Invalid ticker {ticker!r} in {name}")
            if not separator or not company_name or not description:
                raise ConfigurationError(f"{ticker} in {name} must use Ticker: Name; Description")
            members.append(Company(ticker, company_name, description))
        categories[name] = tuple(members)
    universe = Universe(categories)
    _ = universe.companies
    return universe


def load_config(root: Path | None = None) -> ProjectConfig:
    root = (root or project_root()).resolve()
    settings = _read_yaml(root / "config" / "settings.yaml")
    _validate_settings(settings)
    universe = _load_universe(_read_markdown_frontmatter(root / "inputs" / "companies.md"))
    config = ProjectConfig(root=root, settings=settings, universe=universe, available_universe=universe)
    default_scope = str(settings.get("report", {}).get("slug") or next(iter(settings["report_profiles"])))
    if default_scope in settings["report_profiles"]:
        try:
            return config.for_scope(default_scope)
        except ConfigurationError:
            # Preserve useful behavior for callers editing a temporary company
            # fixture before its profile category list is updated.
            return config
    return config
