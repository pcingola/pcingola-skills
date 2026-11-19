#!/usr/bin/env python3
"""
Reads claude --output-format stream-json from stdin line by line
and prints a human-friendly summary to stdout.
"""
import sys
import json


def format_event(obj: dict) -> None:
    t = obj.get("type", "")

    if t == "assistant":
        for blk in obj.get("message", {}).get("content", []):
            blk_type = blk.get("type", "")
            if blk_type == "text":
                text = blk.get("text", "").strip()
                if text:
                    print(text, flush=True)
            elif blk_type == "tool_use":
                name = blk.get("name", "")
                inp  = blk.get("input", {})
                detail = (
                    inp.get("file_path") or
                    inp.get("path") or
                    inp.get("pattern") or
                    inp.get("command") or
                    inp.get("skill") or
                    ""
                )
                if detail:
                    print(f"  → {name}: {detail}", flush=True)
                else:
                    print(f"  → {name}", flush=True)

    elif t == "tool_result":
        if obj.get("is_error"):
            print(f"  ✗ tool error: {obj.get('content', '')}", flush=True)

    elif t == "result":
        result = obj.get("result", "").strip()
        if result:
            print("", flush=True)
            print("── RESULT ──────────────────────────────────────────────", flush=True)
            print(result, flush=True)


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            format_event(json.loads(line))
        except json.JSONDecodeError:
            pass
