#!/usr/bin/env python3
"""Create local secrets without printing them or changing configured values."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import secrets
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    path = ROOT / ".env"
    source = path.read_text() if path.exists() else (ROOT / ".env.example").read_text()
    lines: list[str] = []
    for line in source.splitlines():
        if line.startswith("POSTGRES_PASSWORD=") and line.partition("=")[2] in {
            "", "replace-with-a-random-local-password"
        }:
            line = "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32)
        if line == "CONNECTOR_SECRET_KEY=":
            line = "CONNECTOR_SECRET_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        lines.append(line)
    descriptor, temporary = tempfile.mkstemp(prefix=".env-", dir=ROOT)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(".env configurado com permissões 0600. Valores existentes foram preservados.")


if __name__ == "__main__":
    main()
