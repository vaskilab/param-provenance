"""Field-level source rules.

A JSON Schema constraint says what shape a value must have. A source rule says
where the value is allowed to come from. The second is what catches fabrication.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ABORT = "abort"
WARN = "warn"
_VALID_POLICIES = {ABORT, WARN}


class RuleError(Exception):
    """The rule document is malformed."""


@dataclass(frozen=True)
class SourceRule:
    tool: str
    """The tool whose result must contain the value."""

    path: str
    """Dotted path inside that result, e.g. 'tickets[].ticketId'."""

    on_missing: str = ABORT
    """abort: block the call. warn: record the violation but allow it."""

    @property
    def origin(self) -> str:
        return f"{self.tool}.{self.path}"


@dataclass
class RuleSet:
    rules: dict[str, dict[str, SourceRule]]

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> RuleSet:
        tools = document.get("tools")
        if not isinstance(tools, dict):
            raise RuleError("rule document must contain a 'tools' object")

        parsed: dict[str, dict[str, SourceRule]] = {}
        for tool_name, params in tools.items():
            if not isinstance(params, dict):
                raise RuleError(f"params of tool {tool_name!r} must be an object")
            parsed[tool_name] = {}
            for param_name, spec in params.items():
                parsed[tool_name][param_name] = _parse_rule(tool_name, param_name, spec)
        return cls(parsed)

    @classmethod
    def from_json(cls, text: str) -> RuleSet:
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_file(cls, path: str | Path) -> RuleSet:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def rule_for(self, tool: str, param: str) -> SourceRule | None:
        return self.rules.get(tool, {}).get(param)

    def constrained_params(self, tool: str) -> list[str]:
        return list(self.rules.get(tool, {}).keys())


def _parse_rule(tool_name: str, param_name: str, spec: Any) -> SourceRule:
    where = f"{tool_name}.{param_name}"
    if not isinstance(spec, dict):
        raise RuleError(f"{where}: rule must be an object")

    source = spec.get("source")
    if not isinstance(source, dict):
        raise RuleError(f"{where}: missing 'source' object")

    src_tool = source.get("tool")
    src_path = source.get("path")
    if not isinstance(src_tool, str) or not src_tool:
        raise RuleError(f"{where}: source.tool must be a non-empty string")
    if not isinstance(src_path, str) or not src_path:
        raise RuleError(f"{where}: source.path must be a non-empty string")

    policy = spec.get("on_missing", ABORT)
    if policy not in _VALID_POLICIES:
        raise RuleError(f"{where}: on_missing must be one of {sorted(_VALID_POLICIES)}")

    return SourceRule(tool=src_tool, path=src_path, on_missing=policy)
