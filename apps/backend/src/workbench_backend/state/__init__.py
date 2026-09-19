"""Application SQLite records, separate from the LangGraph checkpointer.

STATE-001: ``application.sqlite`` is the workbench system of record for run
and chat linkage. ``checkpoints.sqlite`` is owned by LangGraph. Application
code stores checkpoint ids only and never mutates checkpointer private tables.

STATE-002: Chat history in the application DB is not the working project.

This package ``__init__`` is import-light on purpose so ``agents.schemas`` can
load ``state.schemas.RelatedFile`` without a cycle through migrate/store.
"""
