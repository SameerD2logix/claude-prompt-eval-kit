from pathlib import Path
from types import SimpleNamespace

import yaml

from prompt_eval.graders import Verdict, run_checks
from prompt_eval.runner import render_prompt, run_suite, to_markdown

SUITE = yaml.safe_load((Path(__file__).resolve().parents[1] / "examples" / "support-replies.yaml").read_text())


def test_code_checks():
    out = '```json\n{"a": 1}\n```'
    r = {c.name: c for c in run_checks(out, {"json_valid": ["a", "b"], "contains": "A", "max_words": 1})}
    assert not r["json_valid"].passed and "missing keys: ['b']" in r["json_valid"].detail
    assert r["contains"].passed  # case-insensitive
    assert not r["max_words"].passed
    r2 = run_checks("Hello team", {"regex": "(?i)TEAM", "not_contains": ["refund"], "bogus": 1})
    assert [c.passed for c in r2] == [True, True, False]


def test_render_prompt():
    assert render_prompt("Hi {{name}}, {{x}}", {"name": "Ali", "x": 2}) == "Hi Ali, 2"


class FakeClient:
    """Answers every prompt the same way; the judge passes unless the answer promises a refund."""

    def __init__(self, answer):
        self.answer = answer
        self.messages = SimpleNamespace(create=self.create, parse=self.parse)

    def create(self, **kw):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.answer)],
                               stop_reason="end_turn", usage=SimpleNamespace(output_tokens=42))

    def parse(self, **kw):
        assert kw["output_format"] is Verdict
        ok = "refund mil jayega" not in kw["messages"][0]["content"]
        return SimpleNamespace(parsed_output=Verdict(passed=ok, reason="ok" if ok else "promised refund"), stop_reason="end_turn")


def test_suite_runs_and_reports():
    good = "Maazrat! Hamari team aap ki request aur address check karke confirm karegi. Order number bata dein."
    results = run_suite(FakeClient(good), SUITE, "claude-opus-5-5", "low", workers=2)
    assert [r.passed for r in results] == [True, True, True]
    md = to_markdown(SUITE, results, "claude-opus-5-5")
    assert "**3/3 passed (100%)**" in md and "126 output tokens" in md


def test_bad_answer_fails_with_reasons():
    bad = "Fikar na karein, refund mil jayega!"
    results = run_suite(FakeClient(bad), SUITE, "claude-opus-5-5", "low", workers=1)
    refund = next(r for r in results if r.id == "refund-demand")
    assert not refund.passed
    details = " ".join(c.detail for c in refund.checks)
    assert "refund mil jayega" in details and "promised refund" in details
