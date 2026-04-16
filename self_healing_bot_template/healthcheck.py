from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


host = os.getenv("HEALTH_HOST", "127.0.0.1")
port = os.getenv("HEALTH_PORT", "8080")
URL = f"http://{host}:{port}/health"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 1

    if payload.get("healthy") is True:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
