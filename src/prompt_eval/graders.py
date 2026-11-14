"""Checks that grade one model output. Code checks are free and deterministic; `judge` asks Claude."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


class Verdict(BaseModel):
    passed: bool = Field(description="true only if the answer fully meets the rubric")
    reason: str = Field(description="one sentence explaining the decision")


JUDGE_SYSTEM = """You grade one AI answer against a rubric. Be strict and literal.
Pass only if every point in the rubric is met. Ignore style unless the rubric mentions it."""


def _contains(out: str, arg) -> CheckResult:
    needles = arg if isinstance(arg, list) else [arg]
    missing = [n for n in needles if n.lower() not in out.lower()]
    return CheckResult("contains", not missing, f"missing: {missing}" if missing else "")


def _not_contains(out: str, arg) -> CheckResult:
    needles = arg if isinstance(arg, list) else [arg]
    found = [n for n in needles if n.lower() in out.lower()]
    return CheckResult("not_contains", not found, f"found: {found}" if found else "")


def _regex(out: str, arg) -> CheckResult:
    ok = re.search(arg, out, re.MULTILINE) is not None
    return CheckResult("regex", ok, "" if ok else f"no match for /{arg}/")


def _max_words(out: str, arg) -> CheckResult:
    n = len(out.split())
    return CheckResult("max_words", n <= int(arg), f"{n} words (max {arg})")


def _json_valid(out: str, arg) -> CheckResult:
    text = out.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    try:
        data = json.loads(fenced.group(1) if fenced else text)
    except json.JSONDecodeError as e:
        return CheckResult("json_valid", False, f"invalid JSON: {e.msg}")
    keys = arg if isinstance(arg, list) else []
    missing = [k for k in keys if not isinstance(data, dict) or k not in data]
    return CheckResult("json_valid", not missing, f"missing keys: {missing}" if missing else "")


CODE_CHECKS: dict[str, Callable[[str, object], CheckResult]] = {
    "contains": _contains,
    "not_contains": _not_contains,
    "regex": _regex,
    "max_words": _max_words,
    "json_valid": _json_valid,
}


def judge(client, model: str, question: str, output: str, rubric: str) -> CheckResult:
    """LLM-as-judge with a structured verdict (always a bool + reason, never free text to parse)."""
    response = client.messages.parse(
        model=model,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content":
                   f"<question>\n{question}\n</question>\n<answer>\n{output}\n</answer>\n<rubric>\n{rubric}\n</rubric>"}],
        output_format=Verdict,
    )
    v: Verdict | None = response.parsed_output
    if v is None:
        return CheckResult("judge", False, f"judge returned nothing (stop_reason={response.stop_reason})")
    return CheckResult("judge", v.passed, v.reason)


def run_checks(output: str, checks: dict, judge_fn: Callable[[str], CheckResult] | None = None) -> list[CheckResult]:
    results = []
    for name, arg in checks.items():
        if name == "judge":
            if judge_fn is None:
                results.append(CheckResult("judge", False, "judge requested but no client"))
            else:
                results.append(judge_fn(arg))
        elif name in CODE_CHECKS:
            results.append(CODE_CHECKS[name](output, arg))
        else:
            results.append(CheckResult(name, False, f"unknown check '{name}'"))
    return results
