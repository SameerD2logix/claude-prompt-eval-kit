"""Run a YAML eval suite against Claude and write a Markdown + JSON report.

Usage: prompt-eval suite.yaml [--model claude-opus-5-5] [--effort medium] [--workers 4] [--out report]
Exit code 1 when the pass rate is below the suite's `pass_threshold` (default 0.9), so it can gate CI.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

import yaml

from .graders import CheckResult, judge, run_checks

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class CaseResult:
    id: str
    input: str
    output: str
    checks: list[CheckResult] = field(default_factory=list)
    seconds: float = 0.0
    output_tokens: int = 0
    error: str = ""

    @property
    def passed(self) -> bool:
        return not self.error and all(c.passed for c in self.checks)


def render_prompt(template: str, case: dict) -> str:
    out = template
    for k, v in case.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def run_case(client, suite: dict, case: dict, model: str, effort: str) -> CaseResult:
    prompt = render_prompt(suite["prompt"], case)
    res = CaseResult(id=str(case.get("id", "?")), input=prompt, output="")
    start = time.time()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=suite.get("max_tokens", 4000),
            output_config={"effort": effort},
            **({"system": suite["system"]} if suite.get("system") else {}),
            messages=[{"role": "user", "content": prompt}],
        )
        res.output = "".join(b.text for b in response.content if b.type == "text")
        res.output_tokens = getattr(response.usage, "output_tokens", 0)
        if response.stop_reason == "refusal":
            res.error = "model declined (refusal)"
    except Exception as e:  # one failing case must not stop the suite
        res.error = f"{type(e).__name__}: {e}"
    res.seconds = round(time.time() - start, 2)
    if not res.error:
        judge_model = suite.get("judge_model", model)
        res.checks = run_checks(res.output, case.get("checks", {}),
                                lambda rubric: judge(client, judge_model, prompt, res.output, rubric))
    return res


def to_markdown(suite: dict, results: list[CaseResult], model: str) -> str:
    passed = sum(r.passed for r in results)
    lines = [f"# Eval report: {suite.get('name', 'suite')}", "",
             f"**{passed}/{len(results)} passed ({passed / max(len(results), 1):.0%})** · model `{model}` · "
             f"{sum(r.output_tokens for r in results)} output tokens", "",
             "| Case | Result | Failed checks | Time |", "|---|---|---|---|"]
    for r in results:
        failed = "; ".join(f"{c.name}: {c.detail}" for c in r.checks if not c.passed) or r.error
        lines.append(f"| {r.id} | {'✅' if r.passed else '❌'} | {failed.replace('|', '/')} | {r.seconds}s |")
    return "\n".join(lines) + "\n"


def run_suite(client, suite: dict, model: str, effort: str, workers: int) -> list[CaseResult]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda c: run_case(client, suite, c, model, effort), suite["cases"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="prompt-eval", description=__doc__.splitlines()[0])
    ap.add_argument("suite")
    ap.add_argument("--model", default=None)
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="eval-report", help="writes <out>.md and <out>.json")
    args = ap.parse_args(argv)

    with open(args.suite, encoding="utf-8") as fh:
        suite = yaml.safe_load(fh)
    model = args.model or suite.get("model", DEFAULT_MODEL)

    import anthropic

    results = run_suite(anthropic.Anthropic(), suite, model, args.effort, args.workers)
    md = to_markdown(suite, results, model)
    with open(f"{args.out}.md", "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(f"{args.out}.json", "w", encoding="utf-8") as fh:
        json.dump([{**asdict(r), "passed": r.passed} for r in results], fh, indent=2, ensure_ascii=False)
    print(md)
    rate = sum(r.passed for r in results) / max(len(results), 1)
    return 0 if rate >= suite.get("pass_threshold", 0.9) else 1


if __name__ == "__main__":
    sys.exit(main())
