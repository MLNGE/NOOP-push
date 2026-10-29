"""Data models for NOOP Push."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReceiverState:
    """Persisted receiver identity."""

    receiver_state_id: str
    version: int
