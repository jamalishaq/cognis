from __future__ import annotations

import re


def extract_json(text: str) -> str:
    """Extract a JSON object from model output that may contain prose or code fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        if inner.strip():
            return inner.strip()
    m = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text
