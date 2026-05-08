#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse a Claude Code JSONL conversation log into an Intricate session.json.

Each user and assistant message becomes a node, connected in sequence.
User messages → WarmNode, Assistant messages → TextNode.
Full text preserved, no truncation.

Usage:
    python generate_chat_session.py <jsonl_path> [output_path]
"""

import json
import sys
import uuid as _uuid
from pathlib import Path


# Layout constants
COL_WIDTH   = 500.0
NODE_WIDTH  = 450.0
ROW_GAP     = 30.0
CHARS_PER_HEIGHT_UNIT = 3.0
MIN_HEIGHT  = 80.0
MAX_HEIGHT  = 400.0


def extract_text(message: dict) -> str:
    """Extract plain text from a message content field."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool: {block.get('name', '?')}]")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def estimate_height(text: str) -> float:
    """Estimate node height from text length."""
    lines = text.count("\n") + 1
    char_h = len(text) / CHARS_PER_HEIGHT_UNIT
    h = max(lines * 16, char_h)
    return max(MIN_HEIGHT, min(MAX_HEIGHT, h))


def parse_jsonl(jsonl_path: str) -> list[dict]:
    """Parse the JSONL and extract user/assistant messages in order."""
    messages = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = d.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            message = d.get("message", {})
            text = extract_text(message)
            timestamp = d.get("timestamp", "")

            if not text.strip():
                continue

            messages.append({
                "role": msg_type,
                "text": text.strip(),
                "timestamp": timestamp,
            })

    return messages


def build_session(messages: list[dict]) -> dict:
    """Build an Intricate session.json from parsed messages."""
    nodes = []
    connections = []

    y_user = 0.0
    y_assistant = 0.0
    prev_uuid = None

    for msg in messages:
        role = msg["role"]
        text = msg["text"]
        node_uuid = _uuid.uuid4().hex
        height = estimate_height(text)

        if role == "user":
            x = 0.0
            y_user = max(y_user, y_assistant)
            y = y_user
            node = {
                "node_type": "warm",
                "uuid": node_uuid,
                "title": f"Human — {msg['timestamp'][:19]}",
                "body_text": text,
                "x": x, "y": y,
                "width": NODE_WIDTH, "height": height,
                "z_value": 0.0,
            }
            y_user += height + ROW_GAP
        else:
            x = COL_WIDTH
            y_assistant = max(y_assistant, y_user - height - ROW_GAP)
            y = max(y_assistant, 0.0)
            node = {
                "node_type": "text",
                "uuid": node_uuid,
                "title": f"Claude — {msg['timestamp'][:19]}",
                "body_text": text,
                "x": x, "y": y,
                "width": NODE_WIDTH, "height": height,
                "z_value": 0.0,
            }
            y_assistant = y + height + ROW_GAP

        nodes.append(node)

        if prev_uuid:
            connections.append({
                "start_uuid": prev_uuid,
                "end_uuid": node_uuid,
            })
        prev_uuid = node_uuid

    return {
        "version": "1.0",
        "description": f"Chat log — {len(messages)} messages",
        "nodes": nodes,
        "connections": connections,
        "viewport": {},
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_chat_session.py <jsonl_path> [output_path]")
        sys.exit(1)

    jsonl_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "Chat_Log_Session.json"

    print(f"Parsing {jsonl_path}...")
    messages = parse_jsonl(jsonl_path)
    print(f"Found {len(messages)} messages")

    session = build_session(messages)
    print(f"Generated {len(session['nodes'])} nodes, {len(session['connections'])} connections")

    # newline="\n" — generated .intricate output is committed alongside the
    # repo; LF matches the eol=lf attribute on tracked session files.
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
