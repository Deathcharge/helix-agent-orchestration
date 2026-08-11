# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Compatibility exports for :mod:`samsarix_orchestration.subprocess_actions`."""

from samsarix_orchestration.subprocess_actions import (
    DEFAULT_MAX_SUBPROCESS_INPUT_BYTES,
    DEFAULT_MAX_SUBPROCESS_STDERR_BYTES,
    DEFAULT_MAX_SUBPROCESS_STDOUT_BYTES,
    MAX_SUBPROCESS_STREAM_BYTES,
    SUBPROCESS_PROTOCOL_VERSION,
    SubprocessActionError,
    SubprocessActionHandler,
    subprocess_action,
    subprocess_envelope,
)

__all__ = [
    "DEFAULT_MAX_SUBPROCESS_INPUT_BYTES",
    "DEFAULT_MAX_SUBPROCESS_STDERR_BYTES",
    "DEFAULT_MAX_SUBPROCESS_STDOUT_BYTES",
    "MAX_SUBPROCESS_STREAM_BYTES",
    "SUBPROCESS_PROTOCOL_VERSION",
    "SubprocessActionError",
    "SubprocessActionHandler",
    "subprocess_action",
    "subprocess_envelope",
]
