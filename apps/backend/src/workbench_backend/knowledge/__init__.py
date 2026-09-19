"""Application-owned durable knowledge store (STATE-005).

Versioned user / agent / project entries live under the product data
``knowledge/`` directory. This is not a checkpointer table, not git, not
``.scratch/``, and not a RAG/retrieval product (OQ-006 remainder stays open).
"""
