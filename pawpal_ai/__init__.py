"""PawPal AI — RAG + agentic health-record extraction layer for PawPal+.

This package extends the base PawPal+ scheduler (see ``pawpal_system.py``) with a
document-ingestion, retrieval-augmented extraction, human-review, and reminder
pipeline for pet health records. See ``docs/system_architecture.mmd`` for the
data flow and ``README.md`` for setup.
"""

__all__ = ["config"]
