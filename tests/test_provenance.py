from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance import (  # noqa: E402
    PARAM_FABRICATION,
    REF_UNRESOLVED,
    RefError,
    RuleError,
    RuleSet,
    Trace,
    check_call,
    extract,
    resolve_args,
    resolve_ref,
)

RULES = RuleSet.from_dict(
    {
        "tools": {
            "urge_ticket": {
                "ticket_id": {
                    "source": {"tool": "query_ticket", "path": "tickets[].ticketId"}
                }
            },
            "annotate_ticket": {
                "ticket_id": {
                    "source": {"tool": "query_ticket", "path": "tickets[].ticketId"},
                    "on_missing": "warn",
                }
            },
        }
    }
)


def trace_with_tickets(tickets, ok=True):
    t = Trace()
    c = t.call("query_ticket", {"user_id": "U1"})
    t.result(c, ok=ok, data={"tickets": tickets})
    return t


class TestExtract(unittest.TestCase):
    def test_wildcard(self):
        data = {"tickets": [{"ticketId": "A"}, {"ticketId": "B"}]}
        self.assertEqual(extract(data, "tickets[].ticketId"), ["A", "B"])

    def test_index(self):
        data = {"tickets": [{"ticketId": "A"}, {"ticketId": "B"}]}
        self.assertEqual(extract(data, "tickets[1].ticketId"), ["B"])

    def test_nested(self):
        data = {"data": {"tickets": [{"ticketId": "A"}]}}
        self.assertEqual(extract(data, "data.tickets[].ticketId"), ["A"])

    def test_missing_path_returns_empty(self):
        self.assertEqual(extract({"tickets": []}, "tickets[].ticketId"), [])
        self.assertEqual(extract({}, "tickets[].ticketId"), [])
        self.assertEqual(extract(None, "tickets[].ticketId"), [])

    def test_out_of_range_index(self):
        self.assertEqual(extract({"tickets": []}, "tickets[0].ticketId"), [])

    def test_scalar_root(self):
        self.assertEqual(extract({"id": "X"}, "id"), ["X"])


class TestChecker(unittest.TestCase):
    def test_legitimate_value_passes(self):
        t = trace_with_tickets([{"ticketId": "T-1"}])
        call = t.call("urge_ticket", {"ticket_id": "T-1"})
        self.assertTrue(check_call(call, t, RULES).ok)

    def test_fabricated_value_blocked(self):
        t = trace_with_tickets([])
        call = t.call("urge_ticket", {"ticket_id": "T-999"})
        result = check_call(call, t, RULES)
        self.assertFalse(result.ok)
        self.assertTrue(result.blocked)
        self.assertEqual(result.violations[0].kind, PARAM_FABRICATION)

    def test_value_from_wrong_tool_blocked(self):
        t = Trace()
        c0 = t.call("query_order", {"user_id": "U1"})
        t.result(c0, ok=True, data={"orders": [{"orderId": "ORD-1"}]})
        c1 = t.call("query_ticket", {"user_id": "U1"})
        t.result(c1, ok=True, data={"tickets": [{"ticketId": "T-1"}]})
        call = t.call("urge_ticket", {"ticket_id": "ORD-1"})
        self.assertFalse(check_call(call, t, RULES).ok)

    def test_failed_source_not_authorized(self):
        t = trace_with_tickets([{"ticketId": "T-1"}], ok=False)
        call = t.call("urge_ticket", {"ticket_id": "T-1"})
        self.assertFalse(check_call(call, t, RULES).ok)

    def test_later_result_not_visible_to_earlier_call(self):
        t = Trace()
        early = t.call("urge_ticket", {"ticket_id": "T-1"})
        c1 = t.call("query_ticket", {"user_id": "U1"})
        t.result(c1, ok=True, data={"tickets": [{"ticketId": "T-1"}]})
        self.assertFalse(check_call(early, t, RULES).ok)

    def test_unconstrained_param_ignored(self):
        t = trace_with_tickets([{"ticketId": "T-1"}])
        call = t.call("urge_ticket", {"ticket_id": "T-1", "note": "free text"})
        self.assertTrue(check_call(call, t, RULES).ok)

    def test_unruled_tool_ignored(self):
        t = Trace()
        call = t.call("some_other_tool", {"anything": "goes"})
        self.assertTrue(check_call(call, t, RULES).ok)

    def test_warn_policy_records_but_allows(self):
        t = trace_with_tickets([])
        call = t.call("annotate_ticket", {"ticket_id": "T-999"})
        result = check_call(call, t, RULES)
        self.assertFalse(result.ok)
        self.assertFalse(result.blocked)

    def test_multiple_results_accumulate_sources(self):
        t = Trace()
        c0 = t.call("query_ticket", {"page": 1})
        t.result(c0, ok=True, data={"tickets": [{"ticketId": "T-1"}]})
        c1 = t.call("query_ticket", {"page": 2})
        t.result(c1, ok=True, data={"tickets": [{"ticketId": "T-2"}]})
        for tid in ("T-1", "T-2"):
            call = t.call("urge_ticket", {"ticket_id": tid})
            self.assertTrue(check_call(call, t, RULES).ok)


class TestRefs(unittest.TestCase):
    def test_ref_resolves_and_passes(self):
        t = trace_with_tickets([{"ticketId": "T-1"}])
        call = t.call("urge_ticket", {"ticket_id": {"$ref": "steps[0].tickets[0].ticketId"}})
        result = check_call(call, t, RULES)
        self.assertTrue(result.ok)
        self.assertEqual(result.resolved_args["ticket_id"], "T-1")

    def test_ref_to_empty_list_blocked(self):
        t = trace_with_tickets([])
        call = t.call("urge_ticket", {"ticket_id": {"$ref": "steps[0].tickets[0].ticketId"}})
        result = check_call(call, t, RULES)
        self.assertFalse(result.ok)
        self.assertEqual(result.violations[0].kind, REF_UNRESOLVED)

    def test_ref_to_failed_result_blocked(self):
        t = trace_with_tickets([{"ticketId": "T-1"}], ok=False)
        call = t.call("urge_ticket", {"ticket_id": {"$ref": "steps[0].tickets[0].ticketId"}})
        self.assertFalse(check_call(call, t, RULES).ok)

    def test_ref_to_missing_step_blocked(self):
        t = trace_with_tickets([{"ticketId": "T-1"}])
        call = t.call("urge_ticket", {"ticket_id": {"$ref": "steps[7].tickets[0].ticketId"}})
        self.assertFalse(check_call(call, t, RULES).ok)

    def test_malformed_ref_raises(self):
        t = trace_with_tickets([{"ticketId": "T-1"}])
        with self.assertRaises(RefError):
            resolve_ref("not-a-ref", t)

    def test_resolve_args_mixed(self):
        t = trace_with_tickets([{"ticketId": "T-1"}])
        out = resolve_args(
            {"ticket_id": {"$ref": "steps[0].tickets[0].ticketId"}, "note": "hi"}, t
        )
        self.assertEqual(out, {"ticket_id": "T-1", "note": "hi"})


class TestRules(unittest.TestCase):
    def test_missing_source_rejected(self):
        with self.assertRaises(RuleError):
            RuleSet.from_dict({"tools": {"x": {"p": {}}}})

    def test_bad_policy_rejected(self):
        with self.assertRaises(RuleError):
            RuleSet.from_dict(
                {
                    "tools": {
                        "x": {
                            "p": {
                                "source": {"tool": "q", "path": "a"},
                                "on_missing": "explode",
                            }
                        }
                    }
                }
            )

    def test_missing_tools_rejected(self):
        with self.assertRaises(RuleError):
            RuleSet.from_dict({})

    def test_example_rules_file_loads(self):
        path = Path(__file__).resolve().parent.parent / "examples" / "rules.json"
        rs = RuleSet.from_file(path)
        rule = rs.rule_for("urge_ticket", "ticket_id")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.origin, "query_ticket.tickets[].ticketId")


if __name__ == "__main__":
    unittest.main(verbosity=2)
