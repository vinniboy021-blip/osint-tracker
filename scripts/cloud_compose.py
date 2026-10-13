#!/usr/bin/env python3
"""Use a managed cloud proxy CA as a build secret and ephemeral runtime mount."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ca = Path("/etc/ssl/certs/ca-certificates.crt")
    if not ca.is_file():
        raise SystemExit("Bundle CA do ambiente ausente; não desabilite validação TLS.")
    # JSON is valid YAML. Keep proxy values out of command output and image layers.
    proxy_environment = {name: os.environ[name] for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY") if name in os.environ}
    proxy_environment["NO_PROXY"] = ",".join(filter(None, [proxy_environment.get("NO_PROXY"), "localhost,127.0.0.1,api,web,postgres,redis,ollama"]))
    config: dict[str, object] = {"secrets": {"proxy_ca": {"file": str(ca)}}, "services": {}}
    services = config["services"]
    assert isinstance(services, dict)
    for service in ("migrate", "api", "worker", "beat", "web"):
        trust = {"NODE_EXTRA_CA_CERTS": "/run/cloud-ca.pem"} if service == "web" else {"SSL_CERT_FILE": "/run/cloud-ca.pem", "REQUESTS_CA_BUNDLE": "/run/cloud-ca.pem"}
        services[service] = {
            "build": {"secrets": ["proxy_ca"]},
            "environment": {**proxy_environment, **trust},
            "volumes": [f"{ca}:/run/cloud-ca.pem:ro"],
        }
    with tempfile.TemporaryDirectory(prefix="osint-compose-") as temporary:
        override = Path(temporary) / "cloud.json"
        override.write_text(json.dumps(config))
        subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "-f", str(override), *sys.argv[1:]], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
