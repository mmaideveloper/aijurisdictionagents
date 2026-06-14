"""Minimal runnable MCP JSON-RPC demo for the laws server.

Prerequisite:
    Start local API first (default http://127.0.0.1:8080).

Run public version call:
    python examples/mcp_laws_server_demo.py

Run protected laws search:
    MCP_API_KEY=mcp_... python examples/mcp_laws_server_demo.py search
"""

from __future__ import annotations

import json
import os
import sys
from urllib import request

BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "").strip()


def mcp_call(tool_name: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
    headers = {"Content-Type": "application/json"}
    if MCP_API_KEY:
        headers["Authorization"] = f"Bearer {MCP_API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments or {}},
    }
    req = request.Request(
        url=f"{BASE_URL}/MCP",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with request.urlopen(req) as response:  # nosec B310 - local demo endpoint
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError(f"Unexpected MCP response: {decoded!r}")
    return decoded


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        response = mcp_call("searchLaws", {"query": "zakon", "country_code": "SK", "limit": 5})
    else:
        response = mcp_call("getVersion")
    print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
