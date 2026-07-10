#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def n(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def fmt(value):
    return f"{n(value):,}"


def blended_total(usage):
    cached = max(n(usage.get("cached_input_tokens")), 0)
    input_tokens = max(n(usage.get("input_tokens")) - cached, 0)
    output_tokens = max(n(usage.get("output_tokens")), 0)
    return input_tokens + output_tokens


def context_total(usage):
    total_tokens = usage.get("total_tokens")
    if total_tokens is not None:
        return n(total_tokens)
    input_tokens = max(n(usage.get("input_tokens")), 0)
    output_tokens = max(n(usage.get("output_tokens")), 0)
    return input_tokens + output_tokens


def latest_token_count(transcript_path):
    if not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.is_file():
        return None

    latest = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("type") != "event_msg":
                continue
            payload = item.get("payload") or {}
            if payload.get("type") != "token_count":
                continue
            if payload.get("info"):
                latest = payload
    return latest


def quiet():
    print(json.dumps({"continue": True, "suppressOutput": True}))


def percent(value):
    if 0 < value < 0.01:
        return "<0.01%"
    rounded = round(value, 2)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.2f}%"


def used_percent(rate_limits, key):
    if not isinstance(rate_limits, dict):
        return None
    window = rate_limits.get(key)
    if not isinstance(window, dict):
        return None
    try:
        return float(window.get("used_percent"))
    except (TypeError, ValueError):
        return None


def quota_remaining(rate_limits):
    parts = []
    for label, key in (("5h", "primary"), ("7d", "secondary")):
        current_used = used_percent(rate_limits, key)
        if current_used is None:
            continue
        remaining = max(100.0 - current_used, 0.0)
        parts.append(f"{label} {percent(remaining)}")

    if not parts:
        return None
    return ", ".join(parts)


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        quiet()
        return

    token_count = latest_token_count(hook_input.get("transcript_path"))
    info = (token_count or {}).get("info")
    if not info:
        quiet()
        return

    last = info.get("last_token_usage") or {}
    context_window = info.get("model_context_window")
    turn_tokens = blended_total(last)
    context_tokens = context_total(last)

    parts = [f"Turn: {fmt(turn_tokens)} tok"]

    if context_window:
        context_percent = (context_tokens / n(context_window)) * 100
        parts.append(f"ctx {percent(context_percent)}")

    quota = quota_remaining((token_count or {}).get("rate_limits"))
    if quota:
        parts.append(f"acct left {quota}")

    print(json.dumps({"continue": True, "systemMessage": "; ".join(parts)}))


if __name__ == "__main__":
    main()
