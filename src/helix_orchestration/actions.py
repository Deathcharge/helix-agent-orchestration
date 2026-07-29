"""Small deterministic actions used by the CLI example workflow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .runtime import ActionContext, ActionHandler


def builtin_actions() -> Mapping[str, ActionHandler]:
    """Return a new mapping of provider-free CLI action handlers."""
    return {
        "collect": collect,
        "echo": echo,
        "uppercase": uppercase,
        "word_count": word_count,
    }


def echo(context: ActionContext) -> Any:
    """Return an explicit value, a dependency output, or the workflow input."""
    return _source_value(context)


def uppercase(context: ActionContext) -> str:
    """Uppercase the selected string input."""
    value = _source_value(context)
    if not isinstance(value, str):
        raise TypeError("uppercase requires a string value")
    return value.upper()


def word_count(context: ActionContext) -> dict[str, int]:
    """Count words and characters in the selected string input."""
    value = _source_value(context)
    if not isinstance(value, str):
        raise TypeError("word_count requires a string value")
    return {"words": len(value.split()), "characters": len(value)}


def collect(context: ActionContext) -> dict[str, Any]:
    """Collect dependency outputs by step id."""
    return dict(context.dependencies)


def _source_value(context: ActionContext) -> Any:
    if "value" in context.step.parameters:
        return context.step.parameters["value"]
    if len(context.dependencies) == 1:
        return next(iter(context.dependencies.values()))
    if context.dependencies:
        return dict(context.dependencies)
    if isinstance(context.workflow_input, dict) and "text" in context.workflow_input:
        return context.workflow_input["text"]
    return context.workflow_input
