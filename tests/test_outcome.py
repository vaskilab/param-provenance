from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance.outcome import (  # noqa: E402
    Outcome,
    check_outcome_reply,
    claims_success,
    classify_outcome,
    idempotency_key,
    render_reply,
)


class TestClassify(unittest.TestCase):
    def test_explicit_success(self):
        self.assertIs(classify_outcome(ok=True), Outcome.SUCCESS)

    def test_explicit_failure(self):
        self.assertIs(classify_outcome(ok=False), Outcome.FAILED)

    def test_timeout_is_unknown_even_if_ok_flag_true(self):
        self.assertIs(classify_outcome(ok=True, timed_out=True), Outcome.UNKNOWN)

    def test_timeout_wins_over_counts(self):
        self.assertIs(
            classify_outcome(ok=True, timed_out=True, succeeded=3, total=3),
            Outcome.UNKNOWN,
        )

    def test_batch_all_succeeded(self):
        self.assertIs(classify_outcome(ok=True, succeeded=3, total=3), Outcome.SUCCESS)

    def test_batch_none_succeeded(self):
        self.assertIs(classify_outcome(ok=False, succeeded=0, total=3), Outcome.FAILED)

    def test_batch_partial(self):
        self.assertIs(classify_outcome(ok=False, succeeded=2, total=3), Outcome.PARTIAL)

    def test_invalid_counts_rejected(self):
        with self.assertRaises(ValueError):
            classify_outcome(ok=True, succeeded=4, total=3)
        with self.assertRaises(ValueError):
            classify_outcome(ok=True, succeeded=-1, total=3)


class TestClaimsSuccess(unittest.TestCase):
    def test_positive_zh(self):
        for text in ("已为你催办成功", "已完成催办", "工单已提交", "办好了"):
            self.assertTrue(claims_success(text), text)

    def test_positive_en(self):
        for text in ("Done.", "The ticket has been submitted", "Request completed"):
            self.assertTrue(claims_success(text), text)

    def test_negated_zh_not_counted(self):
        for text in ("未完成催办", "没有成功", "不成功", "尚未提交", "无法处理"):
            self.assertFalse(claims_success(text), text)

    def test_unknown_wording_not_counted(self):
        self.assertFalse(claims_success("未确认：请求已发出，但没有收到结果"))

    def test_neutral_text(self):
        self.assertFalse(claims_success("这个工单目前处于待处理状态"))

    def test_interrogative_not_counted(self):
        # regression: "已生效" inside a question is not an assertion
        for text in ("请核对是否已生效", "有没有已完成", "确认是否已提交"):
            self.assertFalse(claims_success(text), text)

    def test_conditional_not_counted(self):
        for text in ("如果已完成就不用重试", "若已提交请忽略本条"):
            self.assertFalse(claims_success(text), text)


class TestCheckOutcomeReply(unittest.TestCase):
    def test_success_allows_success_wording(self):
        self.assertIsNone(check_outcome_reply(Outcome.SUCCESS, "已完成催办"))

    def test_failed_blocks_success_wording(self):
        v = check_outcome_reply(Outcome.FAILED, "已为你催办成功")
        self.assertIsNotNone(v)
        self.assertTrue(v.blocking)

    def test_unknown_blocks_success_wording(self):
        self.assertIsNotNone(check_outcome_reply(Outcome.UNKNOWN, "已完成"))

    def test_partial_blocks_all_done_wording(self):
        self.assertIsNotNone(check_outcome_reply(Outcome.PARTIAL, "全部已完成"))

    def test_failed_allows_honest_wording(self):
        self.assertIsNone(check_outcome_reply(Outcome.FAILED, "未完成：上游返回错误"))

    def test_unknown_allows_unconfirmed_wording(self):
        self.assertIsNone(
            check_outcome_reply(Outcome.UNKNOWN, "未确认，请在详情页核对是否已生效")
        )


class TestTemplates(unittest.TestCase):
    def test_every_state_has_a_template(self):
        for state in Outcome:
            self.assertIn(state, __import__(
                "provenance.outcome", fromlist=["REPLY_TEMPLATES"]
            ).REPLY_TEMPLATES)

    def test_unknown_template_offers_verification_path(self):
        text = render_reply(Outcome.UNKNOWN, action="催办工单", verify_hint="工单详情页")
        self.assertIn("未确认", text)
        self.assertIn("工单详情页", text)
        self.assertFalse(claims_success(text))

    def test_failed_template_does_not_claim_success(self):
        self.assertFalse(claims_success(render_reply(Outcome.FAILED, action="催办工单")))

    def test_partial_template_shows_counts(self):
        text = render_reply(Outcome.PARTIAL, action="批量催办", succeeded=2, total=5)
        self.assertIn("2", text)
        self.assertIn("5", text)
        self.assertFalse(claims_success(text))

    def test_success_template_claims_success(self):
        self.assertTrue(claims_success(render_reply(Outcome.SUCCESS, action="催办工单")))


class TestIdempotencyKey(unittest.TestCase):
    def test_stable_for_same_business_identity(self):
        a = idempotency_key("urge_ticket", "T-7781", "2026-11-13")
        b = idempotency_key("urge_ticket", "T-7781", "2026-11-13")
        self.assertEqual(a, b)

    def test_differs_for_different_target(self):
        self.assertNotEqual(
            idempotency_key("urge_ticket", "T-1"),
            idempotency_key("urge_ticket", "T-2"),
        )

    def test_empty_parts_rejected(self):
        with self.assertRaises(ValueError):
            idempotency_key("")
        with self.assertRaises(ValueError):
            idempotency_key("a", "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
