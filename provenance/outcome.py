"""Outcome classification and success-claim checking.

A tool call has more than two possible outcomes. Collapsing them into
success/failure is what lets an agent report "done" for a request that timed out.

This module is a heuristic first-pass filter, not a semantic judge. It belongs in
the cheapest tier of an evaluation pipeline; ambiguous wording should fall
through to a higher tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    SUCCESS = "success"
    """Explicit success signal, side effect confirmed."""

    FAILED = "failed"
    """Explicit error, known not to have taken effect."""

    UNKNOWN = "unknown"
    """Request sent, no response. May or may not have taken effect."""

    PARTIAL = "partial"
    """Batch operation, some items took effect and some did not."""


def classify_outcome(
    *,
    ok: bool,
    timed_out: bool = False,
    succeeded: int | None = None,
    total: int | None = None,
) -> Outcome:
    """Map raw transport signals onto four states.

    Timeout wins over everything else: without a response you cannot know
    whether the write landed, regardless of what the caller hoped for.
    """
    if timed_out:
        return Outcome.UNKNOWN
    if succeeded is not None and total is not None:
        if total < 0 or succeeded < 0 or succeeded > total:
            raise ValueError("succeeded/total must satisfy 0 <= succeeded <= total")
        if succeeded == total:
            return Outcome.SUCCESS if ok else Outcome.PARTIAL
        if succeeded == 0:
            return Outcome.FAILED
        return Outcome.PARTIAL
    return Outcome.SUCCESS if ok else Outcome.FAILED


# Phrases that assert an action took effect. Deliberately conservative.
_SUCCESS_PATTERNS = (
    r"已完成", r"已提交", r"已处理", r"已受理", r"已催办", r"已登记", r"已生效",
    r"已为你", r"已成功", r"成功了", r"办好了", r"搞定了",
    r"\bdone\b", r"\bcompleted\b", r"\bsucceeded\b", r"\bhas been submitted\b",
)

_NEGATIONS = ("未", "没有", "没", "不", "无法", "未能", "尚未", "别", "勿")

# Interrogative / conditional context: "核对是否已生效" asks, it does not assert.
_NON_ASSERTIVE = ("是否", "有没有", "有无", "是不是", "能否", "可否", "如果", "若", "假如")

_CONTEXT_WINDOW = 6


def claims_success(text: str) -> bool:
    """Whether the reply asserts the action took effect.

    Two exclusion rules are applied to the characters preceding each match:
    negation ("未完成", "没有成功") and interrogative or conditional framing
    ("核对是否已生效", "如果已完成"). This is a cheap filter, not a parser —
    wording it cannot resolve should fall through to a higher evaluation tier.
    """
    lowered = text.lower()
    for pattern in _SUCCESS_PATTERNS:
        for match in re.finditer(pattern, lowered):
            prefix = lowered[max(0, match.start() - _CONTEXT_WINDOW) : match.start()]
            if any(neg in prefix for neg in _NEGATIONS):
                continue
            if any(mark in prefix for mark in _NON_ASSERTIVE):
                continue
            return True
    return False


OUTCOME_CLAIM_MISMATCH = "OUTCOME_CLAIM_MISMATCH"


@dataclass
class OutcomeViolation:
    outcome: Outcome
    reply: str
    kind: str = OUTCOME_CLAIM_MISMATCH
    blocking: bool = True

    def describe(self) -> str:
        return (
            f"reply asserts success but outcome is {self.outcome.value}: {self.reply!r}"
        )


def check_outcome_reply(outcome: Outcome, reply: str) -> OutcomeViolation | None:
    """Block success wording unless the outcome is an explicit success.

    PARTIAL is included on purpose: "all done" for a half-applied batch is the
    same class of lie as reporting success on a 500.
    """
    if outcome is Outcome.SUCCESS:
        return None
    if claims_success(reply):
        return OutcomeViolation(outcome=outcome, reply=reply)
    return None


# Fixed wording per state. Deciding *what to say* becomes a lookup, not a
# generation task. The model fills variables; it does not pick the direction.
REPLY_TEMPLATES: dict[Outcome, str] = {
    Outcome.SUCCESS: "已完成：{action}。",
    Outcome.FAILED: "未完成：{action}失败（{reason}）。需要我重试还是转人工？",
    Outcome.UNKNOWN: (
        "未确认：{action}的请求已发出，但没有收到结果。"
        "请在{verify_hint}核对是否已生效，再决定是否重试。"
    ),
    Outcome.PARTIAL: (
        "部分完成：{action}共 {total} 项，成功 {succeeded} 项，"
        "其余未生效。未生效的部分需要单独处理。"
    ),
}


def render_reply(
    outcome: Outcome,
    *,
    action: str,
    reason: str = "上游返回错误",
    verify_hint: str = "记录详情页",
    succeeded: int = 0,
    total: int = 0,
) -> str:
    """Render the fixed template for a state. Never asserts success on its own."""
    return REPLY_TEMPLATES[outcome].format(
        action=action,
        reason=reason,
        verify_hint=verify_hint,
        succeeded=succeeded,
        total=total,
    )


def idempotency_key(*parts: str) -> str:
    """Stable key for retrying an UNKNOWN outcome without double-applying it.

    Retrying a timeout is only safe when the server can deduplicate. The key
    must be derived from business identity, not from a fresh random value.
    """
    if not parts or any(not p for p in parts):
        raise ValueError("idempotency key needs at least one non-empty part")
    return ":".join(parts)
