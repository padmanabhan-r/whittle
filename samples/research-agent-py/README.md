# Research agent (Python sample)

Answers a research question from a small built-in corpus, with a search tool
and a source check. It works, and it wastes money in five ways Whittle is built
to find:

| Waste | Where |
|---|---|
| Changing cache prefix | `agent/loop.py`, `_system_prompt`: the run's timestamp and id sit at the top of the system prompt |
| Context bloat | `agent/loop.py`, `run_pass`: every passage gathered so far is resent on every turn |
| Duplicate tool call | `agent/loop.py`, `run_task`: the answer pass starts a fresh conversation and searches again |
| Oversized model | `agent/config.py`: the one-word classification step runs on the largest model |
| Doomed retry | `agent/loop.py`, `run_pass`: a failed tool call resends the identical request twice |

Run one task against the Anthropic API, or through the Whittle proxy by setting
`ANTHROPIC_BASE_URL`:

```bash
pip install -r requirements.txt
python run.py --task 1
python run.py "Which open-source vector databases support hybrid search?"
```

The answer is printed to standard output. `agent/tasks.py` lists the five
tasks with the words a correct answer must mention.
