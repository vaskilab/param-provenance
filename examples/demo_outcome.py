"""Runnable demonstration of false success reporting.

    python examples/demo_outcome.py

No dependencies, no network, no API key. Same neutral ticket-assistant setting
as demo.py, so the two demos read as a pair.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance.outcome import (  # noqa: E402
    Outcome,
    check_outcome_reply,
    classify_outcome,
    idempotency_key,
    render_reply,
)

LINE = "-" * 72


def header(n: int, title: str) -> None:
    print(f"\n{LINE}\nCASE {n}: {title}\n{LINE}")


def show(outcome: Outcome, reply: str) -> bool:
    print(f"  outcome   : {outcome.value}")
    print(f"  reply     : {reply}")
    violation = check_outcome_reply(outcome, reply)
    print(f"  verdict   : {'BLOCK' if violation else 'ALLOW'}")
    if violation:
        print(f"  [{violation.kind}] {violation.describe()}")
    return violation is None


def case_1_error_reported_as_done() -> None:
    header(1, "The bug: upstream returned 500, agent said it was done")
    outcome = classify_outcome(ok=False)
    print("  urge_ticket -> HTTP 500\n")
    assert not show(outcome, "已为你催办成功")
    print(
        "\n  Nothing landed. But the user now believes it did, and stops asking.\n"
        "  There is no record to reconcile against, so no dashboard fires."
    )


def case_2_timeout_is_not_failure() -> None:
    header(2, "Timeout is a third state, not a failure")
    outcome = classify_outcome(ok=True, timed_out=True)
    print("  urge_ticket -> request sent, no response\n")
    assert not show(outcome, "已完成催办")
    print("\n  And reporting failure is equally wrong:\n")
    honest = render_reply(outcome, action="催办工单", verify_hint="工单详情页")
    assert show(outcome, honest)
    print(
        "\n  The write may or may not have landed. The only honest reply says\n"
        "  'unconfirmed' and hands the user a way to verify."
    )


def case_3_partial_batch() -> None:
    header(3, "Partial success is not success")
    outcome = classify_outcome(ok=False, succeeded=2, total=5)
    print("  batch_urge -> 2 of 5 applied\n")
    assert not show(outcome, "全部已完成")
    print()
    assert show(
        outcome,
        render_reply(outcome, action="批量催办", succeeded=2, total=5),
    )


def case_4_real_success_passes() -> None:
    header(4, "Control: a confirmed success is allowed through")
    outcome = classify_outcome(ok=True)
    print("  urge_ticket -> 200, record written\n")
    assert show(outcome, render_reply(outcome, action="催办工单"))
    print("\n  No false positive on the happy path.")


def case_5_wording_is_a_lookup() -> None:
    header(5, "Deciding what to say is a lookup, not a generation task")
    signals = [
        ("200 + record written", dict(ok=True)),
        ("HTTP 500", dict(ok=False)),
        ("no response", dict(ok=True, timed_out=True)),
        ("2 of 5 applied", dict(ok=False, succeeded=2, total=5)),
    ]
    for label, kwargs in signals:
        outcome = classify_outcome(**kwargs)
        text = render_reply(
            outcome,
            action="催办工单",
            reason="上游返回 500",
            verify_hint="工单详情页",
            succeeded=2,
            total=5,
        )
        violation = check_outcome_reply(outcome, text)
        print(f"  {label:<22} -> {outcome.value:<8} | {'OK' if not violation else 'BAD'}")
        print(f"    {text}")
        assert violation is None
    print(
        "\n  The model fills in variables. It never chooses whether to say\n"
        "  'done' or 'not done' — the state machine already decided."
    )


def case_6_retry_needs_a_key() -> None:
    header(6, "Retrying an UNKNOWN outcome needs a stable key")
    first = idempotency_key("urge_ticket", "T-7781", "2026-11-13")
    retry = idempotency_key("urge_ticket", "T-7781", "2026-11-13")
    other = idempotency_key("urge_ticket", "T-9999", "2026-11-13")
    print(f"  first attempt : {first}")
    print(f"  retry         : {retry}")
    print(f"  other ticket  : {other}")
    assert first == retry and first != other
    print(
        "\n  Same business identity produces the same key, so the server can\n"
        "  deduplicate. A fresh random key per retry would double-apply the write."
    )


def main() -> int:
    print("param-provenance — false success reporting demo")
    print("A tool call has four outcomes, not two.")
    case_1_error_reported_as_done()
    case_2_timeout_is_not_failure()
    case_3_partial_batch()
    case_4_real_success_passes()
    case_5_wording_is_a_lookup()
    case_6_retry_needs_a_key()
    print(f"\n{LINE}\nAll six cases behaved as expected.\n{LINE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
