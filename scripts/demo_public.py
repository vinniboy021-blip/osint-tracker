#!/usr/bin/env python3
"""Demonstração mínima contra um endpoint público e somente-leitura do GitHub.

Não escreve na plataforma e nunca trata a resposta como evidência de investigação.
Defina DEMO_URL para apontar para outro repositório público, se desejar.
"""
import json
import os
import sys
import urllib.error
import urllib.request

DEMO_URL = os.getenv("DEMO_URL", "https://api.github.com/repos/psf/requests")

request = urllib.request.Request(
    DEMO_URL,
    headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "osint-tracker-demo",
    },
)

try:
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
except urllib.error.HTTPError as exc:
    print(f"Erro HTTP {exc.code}: {exc.reason}", file=sys.stderr)
    sys.exit(1)
except urllib.error.URLError as exc:
    print(f"Erro de rede: {exc.reason}", file=sys.stderr)
    sys.exit(1)

print(
    json.dumps(
        {
            "test_source": DEMO_URL,
            "name": payload.get("full_name"),
            "stars": payload.get("stargazers_count"),
        },
        ensure_ascii=False,
    )
)
