"""Recording model proxy: forwards LLM calls and emits neatlogs traces."""

from costcutter.proxy.app import app, create_app

__all__ = ["app", "create_app"]
