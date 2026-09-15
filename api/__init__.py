"""FastAPI backend for PawPal+, the replacement for the retired Streamlit app.

This package exposes pawpal_system.py (scheduler domain) and pawpal_ai/ (RAG /
health-records domain) as a REST API, and -- since the Phase 5 cutover -- also
serves the built React frontend from the same process (api/main.py). The old
app.py / pages/ Streamlit entry points this replaced no longer exist; see
MIGRATION_PLAN.md for the phased rollout that got here.
"""
