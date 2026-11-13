"""The provenance check itself.

Runs before a tool is executed. No model involvement, no network, no cost —
which is why this class of hallucination belongs in the cheapest evaluation tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rules import ABORT, RuleSet
from .trace import (
    REF_KEY,
    RefError,
    ToolCall,
    Trace,
    extract,
    hashable,
    is_ref,
    resolve_ref,
)

PARAM_FABRICATION = "PARAM_FABRICATION"
REF_UNRESOLVED = "REF_UNRESOLVED"


@dataclass
class Violation:
    kind: str
    tool: str
    param: str
    value: Any = None
    expected_source: str | None = None
    detail: str | None = None
    blocking: bool = True

    def describe(self) -> str:
        if self.kind == PARAM_FABRICATION:
            return (
                f"{self.tool}.{self.param}={self.value!r} has no provenance; "
                f"expected a value from {self.expected_source}"
            )
        return f"{self.tool}.{self.param}: {self.detail}"


@dataclass
class CheckResult:
    ok: bool
    resolved_args: dict[str, Any] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(v.blocking for v in self.violations)

    def report(self) -> str:
        if self.ok:
            return "PASS"
        return "\n".join(
            f"{'BLOCK' if v.blocking else 'WARN '} [{v.kind}] {v.describe()}"
            for v in self.violations
        )


def check_call(call: ToolCall, trace: Trace, ruleset: RuleSet) -> CheckResult:
    """Validate one tool call against recorded provenance.

    Two independent mechanisms are applied per argument:

    1. If the argument is a structured reference, resolve it. An unresolvable
       reference is a hard failure — the model asked for something that is not there.
    2. If a source rule exists for the argument, the resolved value must appear at
       the declared path of a prior *successful* result of the declared tool.

    Mechanism 2 is what catches the subtle case: a value that genuinely exists in
    the trace, but came from the wrong tool. Type checks and "does this ID exist
    somewhere in context" checks both pass that case. Provenance does not.
    """
    violations: list[Violation] = []
    resolved: dict[str, Any] = {}

    for name, raw in call.args.items():
        rule = ruleset.rule_for(call.tool, name)

        if is_ref(raw):
            try:
                value = resolve_ref(raw[REF_KEY], trace)
            except RefError as exc:
                violations.append(
                    Violation(
                        kind=REF_UNRESOLVED,
                        tool=call.tool,
                        param=name,
                        detail=str(exc),
                        blocking=(rule.on_missing if rule else ABORT) == ABORT,
                    )
                )
                continue
        else:
            value = raw

        resolved[name] = value

        if rule is None:
            continue

        allowed = {
            hashable(v)
            for result in trace.successful_results_before(call.step, rule.tool)
            for v in extract(result.data, rule.path)
        }

        if hashable(value) not in allowed:
            violations.append(
                Violation(
                    kind=PARAM_FABRICATION,
                    tool=call.tool,
                    param=name,
                    value=value,
                    expected_source=rule.origin,
                    blocking=rule.on_missing == ABORT,
                )
            )

    return CheckResult(ok=not violations, resolved_args=resolved, violations=violations)
