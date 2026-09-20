"""Application-owned durable knowledge store (STATE-005).

Versioned user / agent / project entries live under the product data
``knowledge/`` directory. This is not a checkpointer table, not git, not
``.scratch/``, and not a retrieval index (STATE-006 derives a per-run vector store).
"""
