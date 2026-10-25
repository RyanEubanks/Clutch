"""Generate quizzes with the real model and see how the SymPy math checker handles them.

Answers: how often does the model write checkable math, how often was its answer key
wrong (and fixed), and how often were questions dropped, and why.

Usage (Ollama must be running; Flask does NOT need to be running):
    python eval_quiz.py                  # 2 quizzes per topic
    python eval_quiz.py --reps 5         # more data
    python eval_quiz.py --topic limits   # one topic (see TOPICS for ids)

Results are saved in eval_results/ as quiz-eval-<time>.md (read this) and .csv.
"""
import argparse
import csv
import os
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Keep the app's import-time database setup away from real student data.
os.environ.setdefault("DATABASE_PATH", str(Path(tempfile.mkdtemp()) / "eval.db"))

import app  # noqa: E402  (uses MODEL_NAME / MODEL_BASE_URL from .env, like the real app)

TOPICS = [
    {"id": "chain-rule", "subject": "Calculus I", "topic": "Chain rule",
     "description": "Derivatives of compositions like (3x+1)^4 and sin(x^2)."},
    {"id": "u-sub", "subject": "Calculus I", "topic": "Integration by substitution",
     "description": "Indefinite and definite integrals using u-substitution."},
    {"id": "limits", "subject": "Calculus I", "topic": "Limits",
     "description": "Limits by direct substitution, factoring 0/0 forms, and limits at infinity."},
    {"id": "trig-derivs", "subject": "Calculus I", "topic": "Derivatives of trig functions",
     "description": "Derivatives of sin, cos, tan, sec and their compositions."},
    {"id": "quadratics", "subject": "Algebra", "topic": "Solving quadratic equations",
     "description": "Factoring and the quadratic formula."},
    {"id": "cells", "subject": "Biology", "topic": "Cell organelles",
     "description": "What the nucleus, mitochondria, ribosomes and cell membrane do."},
]

OUT_DIR = Path(__file__).resolve().parent / "eval_results"


def run_one(topic):
    prompt = app.quiz_prompt(
        n=app.QUIZ_QUESTIONS + 2,
        subject=topic["subject"],
        topic=topic["topic"],
        description=f"About this topic: {topic['description']}\n",
        material="",
    )
    start = time.time()
    report = []
    try:
        raw = app.ask_model([{"role": "user", "content": prompt}], temperature=0.4, json_mode=True)
        usable = app.quiz_questions_from(raw, report=report)
        error = None
    except Exception as exc:
        usable, error = [], f"{type(exc).__name__}: {exc}"
    return {"topic": topic, "seconds": time.time() - start, "report": report,
            "usable": len(usable), "error": error}


def option_lines(result):
    lines = []
    for i, opt in enumerate(result["options"]):
        mark = "  **<- answer key**" if i == result["answer"] else ""
        lines.append(f"   {'ABCD'[i]}. {opt}{mark}")
    return lines


def describe(entry):
    """Markdown for one question the model wrote."""
    raw = entry.get("raw") or {}
    status = entry["status"].upper()
    if entry["kind"] == "reply":
        return [f"- **{status}**: {entry['error']}"]
    if entry["kind"] == "math":
        head = f"- **{status}** math `{entry.get('op')}`: `{raw.get('expr')}`"
        lines = [head]
        if entry["status"] == "dropped":
            lines.append(f"   - why: {entry['error']}")
            lines.append(f"   - model's options: `{raw.get('options')}`, answer `{raw.get('answer')}`")
            return lines
        result = entry["result"]
        lines.append(f"   {result['question']}")
        lines += option_lines(result)
        if entry["status"] == "corrected":
            said = result.get("model_said") or "(no valid answer given)"
            lines.append(f"   - **the model's key was wrong**: it marked {said}")
        return lines
    # concept
    if entry["status"] == "dropped":
        return [f"- **DROPPED** concept: {raw.get('question', '(no question)')}",
                f"   - why: {entry['error']}"]
    result = entry["result"]
    return [f"- **UNCHECKED** concept (read it yourself): {result['question']}"] + option_lines(result)


def summarize(runs):
    statuses = Counter()
    drop_reasons = Counter()
    for run in runs:
        for e in run["report"]:
            statuses[f"{e['kind']}:{e['status']}"] += 1
            if e["status"] == "dropped":
                reason = e["error"].split(":")[0]
                drop_reasons[reason] += 1
    math_total = sum(v for k, v in statuses.items() if k.startswith("math:"))
    checked = statuses["math:checked"] + statuses["math:corrected"]
    return statuses, drop_reasons, math_total, checked


def write_reports(runs, stamp):
    OUT_DIR.mkdir(exist_ok=True)
    statuses, drop_reasons, math_total, checked = summarize(runs)
    full = sum(1 for r in runs if r["usable"] >= app.QUIZ_QUESTIONS)
    avg = sum(r["seconds"] for r in runs) / max(1, len(runs))
    errors = sum(1 for r in runs if r["error"])

    md = [f"# Quiz checker eval ({stamp})", "",
          f"Model: {app.MODEL} | quizzes: {len(runs)} | model errors: {errors} | "
          f"avg time per quiz: {avg:.1f}s", "",
          "## Summary", "",
          f"- Quizzes with enough usable questions ({app.QUIZ_QUESTIONS}) from ONE reply: "
          f"{full}/{len(runs)} (the app also retries once)",
          f"- Math questions written: {math_total}",
          f"  - checked, key was right: {statuses['math:checked']}",
          f"  - checked, **key was wrong and got fixed**: {statuses['math:corrected']}",
          f"  - dropped: {statuses['math:dropped']}",
          f"- Concept questions (can't be checked): {statuses['concept:unchecked']} kept, "
          f"{statuses['concept:dropped']} dropped",
          f"- Replies that weren't usable JSON: {statuses['reply:bad_json']}", ""]
    if math_total:
        md.append(f"Model's math answer key accuracy: "
                  f"{statuses['math:checked']}/{checked} of checkable questions "
                  f"({100 * statuses['math:checked'] / max(1, checked):.0f}%). "
                  f"Students only ever see the fixed key.")
        md.append("")
    if drop_reasons:
        md += ["Why questions were dropped:", ""]
        md += [f"- {reason}: {n}" for reason, n in drop_reasons.most_common()]
        md.append("")
    md.append("Read the UNCHECKED concept questions yourself: nothing verifies them.")
    md.append("")
    for run in runs:
        t = run["topic"]
        md += ["---", "", f"## {t['subject']} / {t['topic']} - {run['usable']} usable, "
               f"{run['seconds']:.1f}s", ""]
        if run["error"]:
            md += [f"**Model request failed:** {run['error']}", ""]
        for entry in run["report"]:
            md += describe(entry)
        md.append("")
    md_path = OUT_DIR / f"quiz-eval-{stamp}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    csv_path = OUT_DIR / f"quiz-eval-{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["topic", "kind", "op", "status", "expr", "question", "answer_key",
                    "model_said", "error"])
        for run in runs:
            for e in run["report"]:
                raw, res = e.get("raw") or {}, e.get("result") or {}
                key = res["options"][res["answer"]] if res else ""
                w.writerow([run["topic"]["id"], e["kind"], e.get("op", ""), e["status"],
                            raw.get("expr", ""), res.get("question", raw.get("question", "")),
                            key, res.get("model_said") or "", e.get("error") or ""])
    return md_path, csv_path, statuses, math_total, checked, full


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reps", type=int, default=2, help="quizzes per topic (default 2)")
    parser.add_argument("--topic", choices=[t["id"] for t in TOPICS], help="only this topic")
    args = parser.parse_args()
    if app.mathcheck is None:
        raise SystemExit("sympy is not installed. Run: pip install -r requirements.txt")

    topics = [t for t in TOPICS if args.topic in (None, t["id"])]
    runs = []
    total = len(topics) * args.reps
    for t in topics:
        for rep in range(args.reps):
            print(f"[{len(runs) + 1}/{total}] {t['topic']} (rep {rep + 1})...", flush=True)
            run = run_one(t)
            runs.append(run)
            counts = Counter(e["status"] for e in run["report"])
            print(f"    {run['seconds']:.1f}s, usable {run['usable']}, " +
                  ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) +
                  (f", ERROR {run['error']}" if run["error"] else ""), flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path, csv_path, statuses, math_total, checked, full = write_reports(runs, stamp)
    print()
    print(f"Math questions: {math_total} | key right: {statuses['math:checked']} | "
          f"key wrong, fixed: {statuses['math:corrected']} | dropped: {statuses['math:dropped']}")
    print(f"Concept (unchecked): {statuses['concept:unchecked']} | full quizzes from one reply: "
          f"{full}/{len(runs)}")
    print(f"Saved {md_path.name} and {csv_path.name} in eval_results/")


if __name__ == "__main__":
    main()
