#!/usr/bin/env python3
"""Consistent PostgreSQL/evidence backup; briefly stop writers in maintenance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ["worker", "beat", "api", "web"]


def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, **kwargs)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default=f"backups/{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    args = parser.parse_args()
    target = Path(args.directory).resolve()
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    run(["stop", *SERVICES])
    try:
        with (target / "database.dump").open("wb") as stream:
            run(["exec", "-T", "postgres", "sh", "-c", 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"'], stdout=stream)
        with (target / "evidence.tar.gz").open("wb") as stream:
            run(["run", "--rm", "--no-deps", "-T", "api", "tar", "-C", "/data/evidence", "-czf", "-", "."], stdout=stream)
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": {name: digest(target / name) for name in ("database.dump", "evidence.tar.gz")},
            "note": "Preserve .env/CONNECTOR_SECRET_KEY separately in protected storage.",
        }
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for path in target.iterdir():
            path.chmod(0o600)
        print(f"Backup consistente concluído: {target}")
    finally:
        run(["up", "-d", "--no-deps", *SERVICES])


if __name__ == "__main__":
    main()
