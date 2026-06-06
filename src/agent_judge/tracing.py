"""W&B Weave tracing setup.

Tracing is a key differentiator for this project: every judge execution
(inputs, derived rubric, individual evaluations, final verdict, confidence,
and prompt-improvement suggestions) is captured as a Weave trace tree via the
`@weave.op` decorators in `judge.py`.

This module makes tracing *opt-in and frictionless*: if no Weave project is
configured (or wandb is not logged in), `init_weave()` degrades to a no-op so
the judge still runs locally without any W&B account.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("agent_judge.tracing")

_INITIALIZED = False
_ENABLED = False


def init_weave() -> bool:
    """Initialize Weave tracing once, if configured.

    Returns True if Weave was successfully initialized, False otherwise.
    Safe to call multiple times (idempotent).
    """
    global _INITIALIZED, _ENABLED

    if _INITIALIZED:
        return _ENABLED

    _INITIALIZED = True

    project = os.getenv("WEAVE_PROJECT", "").strip()
    if not project:
        logger.info(
            "WEAVE_PROJECT not set; Weave tracing disabled (judge still runs)."
        )
        _ENABLED = False
        return False

    try:
        import weave  # imported lazily so the package isn't required at import time

        weave.init(project)
        _ENABLED = True
        logger.info("Weave tracing enabled for project '%s'.", project)
    except Exception as exc:  # pragma: no cover - depends on external service
        # Never let tracing failures break the judge.
        logger.warning(
            "Weave init failed (%s); continuing without tracing.", exc
        )
        _ENABLED = False

    return _ENABLED


def is_enabled() -> bool:
    """Return whether Weave tracing is currently active."""
    return _ENABLED
