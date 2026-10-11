"""Answer quality: did each task's answer hold?

Samples carry the words a correct answer must mention, so their score is
deterministic. A user's repository has no such list; its answers are scored by
a model judge against the baseline answers, and the baseline scores itself 1.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskScore:
    task_id: str
    score: float  # 0 to 1
    passed: bool
    note: str


KEYWORD_THRESHOLD = 0.85
JUDGE_THRESHOLD = 0.85


def keyword_score(answer: str, expect: list[str]) -> TaskScore | None:
    if not expect:
        return None
    text = answer.lower()
    hits = [word for word in expect if word.lower() in text]
    score = len(hits) / len(expect)
    missing = [w for w in expect if w not in hits]
    note = "all expected facts present" if not missing else "missing: " + ", ".join(missing)
    return TaskScore("", score, score >= KEYWORD_THRESHOLD - 1e-9, note)


def score_run(task_id: str, answer: str, exit_code: int, expect: list[str] | None, baseline_answer: str | None, judge) -> TaskScore:
    """One task's score. `judge(baseline, answer) -> float` is used when there are no expected words."""
    if exit_code != 0 or not answer.strip():
        return TaskScore(task_id, 0.0, False, f"the agent exited with {exit_code}" if exit_code else "no answer was printed")
    if expect:
        s = keyword_score(answer, expect)
        assert s is not None
        return TaskScore(task_id, round(s.score, 3), s.passed, s.note)
    if baseline_answer is None:
        return TaskScore(task_id, 1.0, True, "baseline answer recorded")
    if judge is None:
        return TaskScore(task_id, 1.0, True, "no judge configured; answer present")
    score = max(0.0, min(1.0, float(judge(baseline_answer, answer))))
    return TaskScore(task_id, round(score, 3), score >= JUDGE_THRESHOLD, f"judge scored {score:.2f} against the baseline answer")


def phase_score(scores: list[TaskScore]) -> float:
    return round(sum(s.score for s in scores) / len(scores), 3) if scores else 0.0


JUDGE_SYSTEM = """You compare two answers an AI agent gave to the same task: the answer before a code change, and the answer after. Decide whether the new answer is still as good for the person who asked.

Score from 0 to 1. 1.0 means it carries the same facts and conclusions, even if worded differently or shorter. 0.5 means some facts or steps are missing or changed. 0 means it is wrong, empty, an error message, or answers something else. Do not reward length. Reply with the score alone, as a number."""


def model_judge(baseline_answer: str, answer: str) -> float:
    """Score a new answer against the baseline answer with Whittle's own model. Used when a task has no expected words."""
    import re

    from costcutter.agent.llm import LLM

    llm = LLM()
    prompt = f"Answer before the change:\n<before>\n{baseline_answer[:6000]}\n</before>\n\nAnswer after the change:\n<after>\n{answer[:6000]}\n</after>"
    turn = llm.turn(JUDGE_SYSTEM, [], [{"role": "user", "content": prompt}], max_tokens=600)
    found = re.search(r"(?<![\d.])(1(?:\.0+)?|0(?:\.\d+)?)(?![\d.])", turn.text)
    if not found:
        raise ValueError(f"the judge did not return a score: {turn.text[:120]!r}")
    return float(found.group(1))
