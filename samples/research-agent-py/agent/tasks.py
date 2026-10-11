"""The five tasks, with what a correct answer must mention."""

TASKS: list[dict[str, object]] = [
    {
        "id": "task-1",
        "input": "What changed in the EU AI Act obligations for general-purpose models this year?",
        "expect": ["august 2025", "systemic risk", "code of practice"],
    },
    {
        "id": "task-2",
        "input": "Compare the battery chemistries used in grid storage and their cost per kWh.",
        "expect": ["lfp", "sodium", "nmc"],
    },
    {
        "id": "task-3",
        "input": "Summarise the evidence on four-day work weeks and productivity.",
        "expect": ["mixed", "wellbeing"],
    },
    {
        "id": "task-4",
        "input": "Which open-source vector databases support hybrid search, and how do they differ?",
        "expect": ["weaviate", "qdrant", "milvus"],
    },
    {
        "id": "task-5",
        "input": "What are the main causes of the 2026 memory chip shortage?",
        "expect": ["high-bandwidth", "hbm", "capacity"],
    },
]
