from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read JSON state {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_gzip_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read compressed JSON state {path}: {exc}") from exc


def write_gzip_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    temporary.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    os.replace(temporary, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serialize(row.get(key)) for key in fieldnames})


def _serialize(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:.12g}"
    return value


def config_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def atomic_replace_directory(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if destination.exists():
        backup = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}-backup-", dir=destination.parent)
        )
        backup.rmdir()
        os.replace(destination, backup)
    try:
        os.replace(source, destination)
    except Exception:
        if backup and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup and backup.exists():
        shutil.rmtree(backup)
