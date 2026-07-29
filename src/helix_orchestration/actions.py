# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Compatibility exports for :mod:`samsarix_orchestration.actions`."""

from samsarix_orchestration.actions import (
    builtin_actions,
    collect,
    echo,
    uppercase,
    word_count,
)

__all__ = ["builtin_actions", "collect", "echo", "uppercase", "word_count"]
