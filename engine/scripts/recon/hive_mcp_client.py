"""starrocks-db MCP HTTP 客户端（token 来自 bdp-sso，勿写入仓库）。"""
from __future__ import annotations

import os

import json
import re
import subprocess
import uuid
from typing import Any

import requests

def _mcp_url() -> str:
    url = (os.getenv("HIVE_MCP_URL") or "").strip()
    if not url:
        raise RuntimeError("请设置环境变量 HIVE_MCP_URL（见仓根 .env.example）")
    return url


MCP_URL = _mcp_url()


def get_bdp_token() -> str:
    out = subprocess.run(
        ["bdp-sso", "get-token"],
        capture_output=True,
        text=True,
        check=False,
    )
    line = (out.stdout or "").strip().splitlines()[-1] if out.stdout else ""
    if not line.startswith("Bearer "):
        raise RuntimeError(f"bdp-sso get-token failed: {out.stderr or out.stdout}")
    return line.strip()


def _parse_sse_payload(text: str) -> dict[str, Any]:
    data_parts: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_parts.append(line[5:].strip())
    if data_parts:
        blob = "".join(data_parts)
        return json.loads(blob)
    return json.loads(text)


def mcp_call(tool_name: str, arguments: dict[str, Any], token: str) -> Any:
    sess = requests.Session()
    sess.headers.update(
        {
            "Accept": "application/json, text/event-stream",
            "Authorization": token,
        }
    )
    init = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "qdm-engine", "version": "1.0"},
        },
    }
    r = sess.post(MCP_URL, json=init, timeout=120)
    r.raise_for_status()
    sid = r.headers.get("mcp-session-id")
    if sid:
        sess.headers["mcp-session-id"] = sid
    sess.post(MCP_URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=30)

    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": {**arguments, "token": token}},
    }
    r = sess.post(MCP_URL, json=body, timeout=300)
    r.raise_for_status()
    payload = _parse_sse_payload(r.text)
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    result = payload.get("result") or {}
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


def export_query_to_file(sql: str, dest_path: str, token: str | None = None, max_rows: int = 100000) -> str:
    token = token or get_bdp_token()
    raw = mcp_call("export_query", {"sql": sql, "max_rows": max_rows}, token)
    if isinstance(raw, dict) and raw.get("download_url"):
        url = raw["download_url"]
    elif isinstance(raw, str):
        m = re.search(r"https?://[^\s\"']+", raw)
        if not m:
            raise RuntimeError(f"export_query: no download URL in response: {raw[:500]}")
        url = m.group(0)
    else:
        raise RuntimeError(f"unexpected export_query response: {raw!r}")
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    from pathlib import Path

    Path(dest_path).write_bytes(resp.content)
    return dest_path


def query_all_rows(sql: str, token: str | None = None) -> list[dict[str, Any]]:
    token = token or get_bdp_token()
    offset = 0
    rows: list[dict[str, Any]] = []
    cols: list[str] = []
    while True:
        raw = mcp_call("query", {"sql": sql, "offset": offset, "format": "json"}, token)
        if isinstance(raw, str):
            raw = json.loads(raw)
        batch = raw.get("rows") or []
        if not cols:
            cols = raw.get("columns") or []
        if not batch:
            break
        for item in batch:
            if isinstance(item, dict):
                rows.append(item)
            else:
                rows.append({cols[i]: item[i] for i in range(min(len(cols), len(item)))})
        next_off = raw.get("next_offset")
        if next_off is None or next_off == offset or len(batch) == 0:
            break
        offset = int(next_off)
        if offset > 10000:
            break
    return rows
