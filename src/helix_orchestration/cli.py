# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Compatibility exports for :mod:`samsarix_orchestration.cli`."""

from argparse import ArgumentParser

from samsarix_orchestration.cli import EXAMPLE_WORKFLOW, MAX_INPUT_BYTES, legacy_main
from samsarix_orchestration.cli import build_parser as _build_parser


def build_parser() -> ArgumentParser:
    """Build a parser that retains the historical command name."""
    return _build_parser(prog="helix-orchestration")


main = legacy_main

__all__ = [
    "EXAMPLE_WORKFLOW",
    "MAX_INPUT_BYTES",
    "build_parser",
    "legacy_main",
    "main",
]
