"""Model choices for the research agent."""

import os

# The model every step runs on, including the one-word classification step.
MODEL = os.environ.get("RESEARCH_AGENT_MODEL", "claude-sonnet-5-5")
CLASSIFY_MODEL = os.environ.get("RESEARCH_AGENT_CLASSIFY_MODEL", "claude-haiku-5-5")
MAX_TURNS = 6
MAX_TOKENS = 1024
