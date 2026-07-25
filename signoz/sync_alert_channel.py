#!/usr/bin/env python3
"""Sync SigNoz's Slack notification channel from backend/.env.

The webhook URL is a credential, so it lives in backend/.env (gitignored) and
never in casting.yaml (git-tracked). SigNoz stores the channel in its own
database, so changing .env alone has no effect -- run this script to push it.

    python signoz/sync_alert_channel.py

Reads SLACK_WEBHOOK_URL and SIGNOZ_API_KEY from backend/.env, then creates or
updates the channel named by CHANNEL_NAME. Existing alert rules reference the
channel by name, so updating in place keeps all 9 rules wired up.

Options:
    --dry-run   show what would change without calling SigNoz
    --probe     also POST a test message straight to the webhook
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

CHANNEL_NAME = "ai-interview-slack"
SIGNOZ_URL = os.environ.get("SIGNOZ_URL", "http://localhost:8080")
MCP_URL = os.environ.get("SIGNOZ_MCP_URL", "http://localhost:8000/mcp")
ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / "backend" / ".env"


def load_env(path):
    if not path.is_file():
        sys.exit(f"error: {path} not found")
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def redact(text, secret):
    return text.replace(secret, "<REDACTED>") if secret else text


def curl(method, url, api_key, body=None, extra_headers=None):
    """Shell out to curl -- urllib gets its connection reset by this server."""
    cmd = ["curl", "-s", "-w", "\n%{http_code}", "--max-time", "60", "-X", method,
           "-H", f"SIGNOZ-API-KEY: {api_key}", "-H", "Content-Type: application/json"]
    for k, v in (extra_headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    tmp = None
    if body is not None:
        fd, tmp = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(body, f)
        cmd += ["--data-binary", f"@{tmp}"]
    cmd.append(url)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=90).stdout
    finally:
        if tmp:
            os.unlink(tmp)
    payload, _, code = out.rpartition("\n")
    try:
        return int(code or 0), json.loads(payload)
    except Exception:
        return int(code or 0), payload


def mcp(tool, args, api_key):
    code, resp = curl("POST", MCP_URL, api_key,
                      body={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": tool, "arguments": args}},
                      extra_headers={"Accept": "application/json, text/event-stream"})
    if code != 200 or not isinstance(resp, dict):
        return code, str(resp)[:400]
    r = resp.get("result", resp)
    text = "".join(c.get("text", "") for c in (r.get("content") or []))
    return code, text or json.dumps(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    env = load_env(ENV_PATH)
    hook = env.get("SLACK_WEBHOOK_URL")
    api_key = env.get("SIGNOZ_API_KEY")
    channel = env.get("SLACK_CHANNEL")  # optional, e.g. #alerts

    missing = [k for k, v in (("SLACK_WEBHOOK_URL", hook), ("SIGNOZ_API_KEY", api_key)) if not v]
    if missing:
        sys.exit(f"error: missing in {ENV_PATH.name}: {', '.join(missing)}")
    if not hook.startswith("https://hooks.slack.com/services/"):
        print(f"warning: {hook[:40]}... does not look like a Slack incoming webhook")

    print(f"env      : {ENV_PATH}")
    print(f"webhook  : {hook[:44]}...<redacted>")
    print(f"signoz   : {SIGNOZ_URL}")

    if args.probe:
        code, _ = curl("POST", hook, api_key,
                       body={"text": "SigNoz sync_alert_channel.py probe"})
        print(f"probe    : webhook POST -> HTTP {code}")

    code, resp = curl("GET", f"{SIGNOZ_URL}/api/v1/channels", api_key)
    if code != 200 or not isinstance(resp, dict):
        sys.exit(f"error: cannot list channels ({code}): {str(resp)[:200]}")
    existing = next((c for c in (resp.get("data") or [])
                     if c.get("name") == CHANNEL_NAME), None)

    payload = {"type": "slack", "name": CHANNEL_NAME, "slack_api_url": hook,
               "send_resolved": True,
               "searchContext": "sync slack webhook from backend/.env"}
    if channel:
        payload["slack_channel"] = channel

    if args.dry_run:
        action = f"update id={existing['id']}" if existing else "create"
        print(f"dry-run  : would {action} channel '{CHANNEL_NAME}'")
        return

    if existing:
        payload["id"] = existing["id"]
        code, out = mcp("signoz_update_notification_channel", payload, api_key)
        verb = "updated"
    else:
        code, out = mcp("signoz_create_notification_channel", payload, api_key)
        verb = "created"

    out = redact(out, hook)
    if code == 200 and '"error"' not in out[:200].lower():
        print(f"result   : {verb} channel '{CHANNEL_NAME}'")
        print(f"detail   : {out[:200]}")
    else:
        sys.exit(f"error: {verb} failed ({code}): {out[:300]}")

    print("\nAlert rules reference this channel by name, so all rules stay wired.")


if __name__ == "__main__":
    main()
