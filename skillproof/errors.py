"""Operational errors with stable machine-readable codes."""

from __future__ import annotations


class SPError(Exception):
    """A SkillProof operational error.

    ``code`` is a short stable identifier (e.g. ``bad_suite``) that callers and
    tests can match on; the message is human-readable detail.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
