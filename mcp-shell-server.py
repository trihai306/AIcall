#!/usr/bin/env python3
"""Simple MCP shell server — runs shell commands with full system permissions."""
import asyncio
import json
import subprocess
import sys


def send(obj):
    print(json.dumps(obj), flush=True)


def handle(req):
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        send({
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mcp-shell", "version": "1.0.0"}
            }
        })

    elif method == "tools/list":
        send({
            "jsonrpc": "2.0", "id": rid,
            "result": {"tools": [{
                "name": "shell",
                "description": "Run a shell command on the host Mac",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string", "description": "Shell command to run"},
                        "cwd": {"type": "string", "description": "Working directory (optional)"}
                    },
                    "required": ["cmd"]
                }
            }]}
        })

    elif method == "tools/call":
        args = req.get("params", {}).get("arguments", {})
        cmd = args.get("cmd", "")
        cwd = args.get("cwd") or None
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=60, cwd=cwd
            )
            output = result.stdout + result.stderr
            send({
                "jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": output or "(no output)"}]}
            })
        except subprocess.TimeoutExpired:
            send({
                "jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": "ERROR: timeout"}]}
            })
        except Exception as e:
            send({
                "jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}]}
            })

    elif method == "notifications/initialized":
        pass  # no response needed

    else:
        if rid is not None:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(req)


if __name__ == "__main__":
    main()
