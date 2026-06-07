"""Tests for W&B Weave tracing setup."""

import os

from agent_judge.tracing import init_weave, is_enabled


def test_init_weave_noop_without_project(monkeypatch):
    monkeypatch.delenv("WEAVE_PROJECT", raising=False)
    monkeypatch.delenv("WANDB_API_KEY", raising=False)
    # Reset module state for a clean test
    import agent_judge.tracing as tracing

    tracing._INITIALIZED = False
    tracing._ENABLED = False

    enabled = init_weave()
    assert enabled is False
    assert is_enabled() is False


def test_init_weave_idempotent(monkeypatch):
    monkeypatch.delenv("WEAVE_PROJECT", raising=False)
    import agent_judge.tracing as tracing

    tracing._INITIALIZED = False
    tracing._ENABLED = False

    first = init_weave()
    second = init_weave()
    assert first == second
