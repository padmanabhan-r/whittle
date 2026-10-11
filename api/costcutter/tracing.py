"""One neatlogs initialisation for the whole process.

The proxy's run recorder and Whittle's own agent both trace into neatlogs. The SDK
refuses a second init ("Neatlogs is already running"), so both go through here.
"""

from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_ready = False


def ensure_neatlogs(api_key: str | None = None, endpoint: str | None = None, workflow_name: str = "whittle") -> bool:
    """Initialise the SDK once. Returns whether tracing is on."""
    global _ready
    if _ready:
        return True
    key = (api_key or os.environ.get("NEATLOGS_API_KEY", "")).strip()
    if not key:
        return False
    with _lock:
        if _ready:
            return True
        import neatlogs

        try:
            neatlogs.init(api_key=key, endpoint=endpoint or os.environ.get("NEATLOGS_ENDPOINT") or None, workflow_name=workflow_name, debug=False)
        except Exception as exc:  # already running, from another entry point in this process
            if "already" not in str(exc).lower():
                raise
        _ready = True
    return True
