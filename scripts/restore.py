#!/usr/bin/env python3
"""Restore a validated backup into the configured stack (destructive operator action)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backup import SERVICES, digest, run

EXTRACT = """
import sys, tarfile, shutil
from pathlib import Path
root = Path('/data/evidence')
for child in root.iterdir():
    if child.is_dir(): shutil.rmtree(child)
    else: child.unlink()
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as archive:
    archive.extractall(root, filter='data')
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--replace-data", action="store_true", help="Confirma substituição do banco e evidências")
    args = parser.parse_args()
    if not args.replace_data:
        parser.error("A restauração substitui dados. Execute com --replace-data depois de revisar o backup.")
    target = Path(args.directory).resolve()
    manifest = json.loads((target / "manifest.json").read_text())
    for name in ("database.dump", "evidence.tar.gz"):
        if digest(target / name) != manifest["files"][name]:
            raise SystemExit(f"Integridade inválida: {name}")
    run(["stop", *SERVICES])
    try:
        with (target / "database.dump").open("rb") as stream:
            run(["exec", "-T", "postgres", "sh", "-c", 'pg_restore --clean --if-exists --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"'], stdin=stream)
        with (target / "evidence.tar.gz").open("rb") as stream:
            run(["run", "--rm", "--no-deps", "-T", "api", "python", "-c", EXTRACT], stdin=stream)
        run(["run", "--rm", "--no-deps", "migrate"])
        print("Restauração concluída e migrações aplicadas.")
    except Exception:
        print("Restauração falhou; serviços escritores permanecem parados. Examine o erro antes de reiniciar.")
        raise
    else:
        run(["up", "-d", "--no-deps", *SERVICES])


if __name__ == "__main__":
    main()
