"""Runnable demonstration of parameter fabrication and how provenance stops it.

    python examples/demo.py

No dependencies, no network, no API key. Four scenarios, all using a neutral
ticket-assistant setting.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance import RuleSet, Trace, check_call  # noqa: E402

RULES = RuleSet.from_file(Path(__file__).resolve().parent / "rules.json")

LINE = "-" * 72


def header(n: int, title: str) -> None:
    print(f"\n{LINE}\nCASE {n}: {title}\n{LINE}")


def show(call, trace) -> bool:
    result = check_call(call, trace, RULES)
    print(f"  tool      : {call.tool}")
    print(f"  args      : {call.args}")
    if result.resolved_args and result.resolved_args != call.args:
        print(f"  resolved  : {result.resolved_args}")
    print(f"  verdict   : {'ALLOW' if not result.blocked else 'BLOCK'}")
    if not result.ok:
        for line in result.report().splitlines():
            print(f"  {line}")
    return not result.blocked


def base_trace() -> Trace:
    """Context every case shares: an order lookup succeeded, a ticket lookup did not."""
    t = Trace()
    c0 = t.call("query_order", {"user_id": "U10086"})
    t.result(c0, ok=True, data={"orders": [{"orderId": "20261103001"}]})
    return t


def case_1_fabricated() -> None:
    header(1, "The bug: query returned nothing, model borrowed an unrelated ID")
    t = base_trace()
    c1 = t.call("query_ticket", {"user_id": "U10086", "keyword": "last week"})
    t.result(c1, ok=True, data={"tickets": []})
    print("  query_ticket -> {\"tickets\": []}   (user has no tickets)")
    print("  model then reuses the orderId it saw earlier as a ticketId:\n")

    # Format is valid. The ID really exists in the trace. The call would return 200.
    c2 = t.call("urge_ticket", {"ticket_id": "20261103001"})
    allowed = show(c2, t)
    print(
        "\n  Note: schema validation passes here. The value is a string, it is\n"
        "  non-empty, and it does exist somewhere in the context. Only its ORIGIN\n"
        "  is wrong — and origin is what this check inspects."
    )
    assert not allowed


def case_2_legitimate() -> None:
    header(2, "Control: a real ticket ID from the right tool is allowed")
    t = base_trace()
    c1 = t.call("query_ticket", {"user_id": "U10086"})
    t.result(c1, ok=True, data={"tickets": [{"ticketId": "T-7781", "state": "open"}]})
    print("  query_ticket -> tickets[0].ticketId = 'T-7781'\n")

    c2 = t.call("urge_ticket", {"ticket_id": "T-7781"})
    allowed = show(c2, t)
    print("\n  No false positive: legitimate calls go through untouched.")
    assert allowed


def case_3_wrong_source() -> None:
    header(3, "Subtle: value exists in the trace, but came from the wrong tool")
    t = base_trace()
    c1 = t.call("query_ticket", {"user_id": "U10086"})
    t.result(c1, ok=True, data={"tickets": [{"ticketId": "T-7781"}]})
    print("  query_ticket -> 'T-7781'   (valid)")
    print("  query_order  -> '20261103001'   (valid, but it is an ORDER id)\n")

    c2 = t.call("urge_ticket", {"ticket_id": "20261103001"})
    allowed = show(c2, t)
    print(
        "\n  An 'is this ID present anywhere in context' check would allow this.\n"
        "  A field-level source rule does not."
    )
    assert not allowed


def case_4_structural() -> None:
    header(4, "Prevention: the model supplies a path, the engine supplies the value")
    t = base_trace()
    c1 = t.call("query_ticket", {"user_id": "U10086"})
    t.result(c1, ok=True, data={"tickets": [{"ticketId": "T-7781"}]})

    print("  4a. reference into an existing element:\n")
    ok_call = t.call(
        "urge_ticket", {"ticket_id": {"$ref": "steps[1].tickets[0].ticketId"}}
    )
    assert show(ok_call, t)

    print("\n  4b. same shape, but the query had returned an empty list:\n")
    t2 = base_trace()
    c1b = t2.call("query_ticket", {"user_id": "U10086"})
    t2.result(c1b, ok=True, data={"tickets": []})
    bad_call = t2.call(
        "urge_ticket", {"ticket_id": {"$ref": "steps[1].tickets[0].ticketId"}}
    )
    assert not show(bad_call, t2)
    print(
        "\n  The model never held a value it could invent. It asked for element 0\n"
        "  of an empty list, and the engine refused. This is prevention rather\n"
        "  than detection."
    )


def case_5_failed_source() -> None:
    header(5, "A failed query must not authorize a write")
    t = Trace()
    c0 = t.call("query_ticket", {"user_id": "U10086"})
    t.result(c0, ok=False, data={"tickets": [{"ticketId": "T-9999"}]}, error="upstream 500")
    print("  query_ticket -> HTTP 500, but the payload happened to contain an ID\n")

    c1 = t.call("urge_ticket", {"ticket_id": "T-9999"})
    allowed = show(c1, t)
    print("\n  Partial data from a failed call is never a valid source.")
    assert not allowed


def main() -> int:
    print("param-provenance — parameter fabrication demo")
    print("Schema checks the shape of a value. Provenance checks its origin.")
    case_1_fabricated()
    case_2_legitimate()
    case_3_wrong_source()
    case_4_structural()
    case_5_failed_source()
    print(f"\n{LINE}\nAll five cases behaved as expected.\n{LINE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
