"""FastAPI backend for PawPal+, replacing the Streamlit app (see app.py, pages/).

This package exposes pawpal_system.py (scheduler domain) and pawpal_ai/ (RAG /
health-records domain) as a REST API. See the migration plan for the full
phased rollout; only the Phase 0 liveness endpoint exists so far.
"""
