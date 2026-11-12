"""Codex HTTP-header helper for the current Windows user's DPAPI vault.

Use only as a credential helper, not as a diagnostic command. It deliberately
prints a secret-bearing JSON object to its caller's pipe, never to a log.
"""
import json
import os
from pathlib import Path


def read_token():
    supplied = os.environ.get("STL_MCP_TOKEN")
    if supplied:
        return supplied
    import win32crypt
    path = Path(os.environ.get("STL_MCP_TOKEN_FILE", Path(__file__).resolve().parents[2] / ".local/stl-mcp/public-token.dpapi"))
    return win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 0)[1].decode("ascii")


if __name__ == "__main__":
    print(json.dumps({"Authorization": "Bearer " + read_token()}))
