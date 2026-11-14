# Claude Prompt Eval Kit

> **Stop guessing if a prompt change helped.** Write test cases in YAML, run them against Claude, get a pass/fail report, and fail CI when quality drops.

![python](https://img.shields.io/badge/python-3.10%2B-3776AB) ![claude](https://img.shields.io/badge/Claude-evals-D97757) ![license](https://img.shields.io/badge/license-MIT-green)

## Example suite

```yaml
name: Customer support replies (Roman Urdu)
model: claude-opus-5-5
pass_threshold: 0.8
system: |
  You are the support assistant of an online shop in Pakistan. Reply in Roman Urdu,
  politely, in at most 60 words. Never promise refunds.
prompt: |
  Customer message: {{message}}
cases:
  - id: refund-demand
    message: "Mujhe abhi refund chahiye warna review kharab dunga"
    checks:
      not_contains: ["refund kar diya", "refund mil jayega"]
      judge: "Stays calm and polite, does NOT promise a refund, says the team will review the request."
```

## Checks

| Check | Argument | Cost |
|---|---|---|
| `contains` / `not_contains` | string or list (case-insensitive) | free |
| `regex` | Python regex | free |
| `max_words` | number | free |
| `json_valid` | list of required keys (handles ```json fences) | free |
| `judge` | rubric text: Claude grades with a **structured verdict** (`passed` + `reason`) | 1 small call |

Prefer code checks; use `judge` for things code can't see (tone, correctness of advice).

## Run

```bash
pip install git+https://github.com/SameerD2logix/claude-prompt-eval-kit
export ANTHROPIC_API_KEY=...
prompt-eval examples/support-replies.yaml --effort medium --out report
```

```
# Eval report: Customer support replies (Roman Urdu)
**3/3 passed (100%)** · model `claude-opus-5-5` · 312 output tokens
| Case | Result | Failed checks | Time |
|---|---|---|---|
| late-order | ✅ |  | 4.1s |
...
```
Writes `report.md` + `report.json`. Exit code `1` when the pass rate is under `pass_threshold`, so you
can block a merge in GitHub Actions.

## Good eval habits (built into the design)

- Cases run **in parallel** (`--workers`); one failing call doesn't stop the suite.
- Refusals are reported as failures, not hidden. No server-side fallback here on purpose, so the report shows the model you asked for.
- Compare settings fairly: same suite, change one thing (`--effort`, `--model`, or the prompt).
- Keep 20–50 real cases; add every production bug as a new case.

## Tests

```bash
pip install -e . pytest && pytest -q
```
Offline: a fake client stands in for Claude.

## Author

**Sameer Hussain** · [LinkedIn](https://www.linkedin.com/in/sameer-hussain-87368a164) · [D2Logix](https://d2logix.com)
