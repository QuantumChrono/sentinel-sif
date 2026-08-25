"""Preprocessing package. Exposes the one function the inference path calls.

Not a barrel file: it re-exports a single name so callers write
`from backend.preprocessing import clean_report` instead of reaching two levels deep.
Everything else in this package stays internal.
"""

from .clean_report import clean_report

__all__ = ["clean_report"]
