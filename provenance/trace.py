"""Trace model, path extraction, and structured reference resolution.

A trace is an ordered log of tool calls and their results. Provenance checking
asks one question of every constrained argument: which successful tool result,
at which path, produced this value?
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

REF_KEY = "$ref"

_SEGMENT = re.compile(r"([^\[\]]+)|\[(\d*)\]")
_REF_PATTERN = re.compile(r"^steps\[(\d+)\]\.(.+)$")


class RefError(Exception):
    """A structured reference could not be resolved."""


@dataclass
class ToolCall:
    step: int
    tool: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    step: int
    tool: str
    ok: bool
    data: Any = None
    error: str | None = None


@dataclass
class Trace:
    """Ordered sequence of calls and results, with monotonically increasing steps."""

    events: list[Any] = field(default_factory=list)
    _next_step: int = 0

    def call(self, tool: str, args: dict[str, Any]) -> ToolCall:
        c = ToolCall(step=self._next_step, tool=tool, args=dict(args))
        self._next_step += 1
        self.events.append(c)
        return c

    def result(
        self,
        call: ToolCall,
        ok: bool,
        data: Any = None,
        error: str | None = None,
    ) -> ToolResult:
        r = ToolResult(step=call.step, tool=call.tool, ok=ok, data=data, error=error)
        self.events.append(r)
        return r

    def successful_results_before(self, step: int, tool: str) -> list[ToolResult]:
        """Only successful results may authorize a downstream write.

        A failed or partial query must never become a source of valid IDs.
        """
        return [
            e
            for e in self.events
            if isinstance(e, ToolResult) and e.ok and e.step < step and e.tool == tool
        ]

    def result_at(self, step: int) -> ToolResult | None:
        for e in self.events:
            if isinstance(e, ToolResult) and e.step == step:
                return e
        return None


def _tokenize(path: str) -> list[Any]:
    """Split a dotted path into name / index / wildcard tokens.

    'data.tickets[].ticketId' -> ['data', 'tickets', '[]', 'ticketId']
    'steps[1].data.tickets[0].ticketId' -> ['steps', 1, 'data', 'tickets', 0, 'ticketId']
    """
    tokens: list[Any] = []
    for part in path.split("."):
        if not part:
            continue
        for m in _SEGMENT.finditer(part):
            name, idx = m.group(1), m.group(2)
            if name is not None:
                tokens.append(name)
            else:
                tokens.append("[]" if idx == "" else int(idx))
    return tokens


def extract(data: Any, path: str) -> list[Any]:
    """Collect every value reachable at `path`. Supports [] wildcards and [n] indices."""
    nodes = [data]
    for token in _tokenize(path):
        nxt: list[Any] = []
        for node in nodes:
            if token == "[]":
                if isinstance(node, list):
                    nxt.extend(node)
            elif isinstance(token, int):
                if isinstance(node, list) and -len(node) <= token < len(node):
                    nxt.append(node[token])
            else:
                if isinstance(node, dict) and token in node:
                    nxt.append(node[token])
        nodes = nxt
        if not nodes:
            return []
    return nodes


def is_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value.keys()) == {REF_KEY}


def resolve_ref(ref: str, trace: Trace) -> Any:
    """Resolve 'steps[N].<path>' against a recorded successful result.

    The model supplies a path, never a value. The engine does the dereferencing,
    so there is no opportunity to invent an identifier.
    """
    m = _REF_PATTERN.match(ref)
    if not m:
        raise RefError(f"malformed $ref: {ref!r} (expected 'steps[N].<path>')")

    step = int(m.group(1))
    path = m.group(2)

    result = trace.result_at(step)
    if result is None:
        raise RefError(f"no result recorded at step {step}")
    if not result.ok:
        raise RefError(f"result at step {step} was not successful")

    values = extract(result.data, path)
    if not values:
        raise RefError(f"path {path!r} not present in result of step {step}")
    return values[0]


def resolve_args(args: dict[str, Any], trace: Trace) -> dict[str, Any]:
    """Resolve every $ref in an argument map. Raises RefError on the first failure."""
    resolved: dict[str, Any] = {}
    for name, raw in args.items():
        resolved[name] = resolve_ref(raw[REF_KEY], trace) if is_ref(raw) else raw
    return resolved


def hashable(value: Any) -> Any:
    """IDs are normally scalars; fall back to a canonical form for containers."""
    try:
        hash(value)
        return value
    except TypeError:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
