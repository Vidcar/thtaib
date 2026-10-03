"""Application-owned durable knowledge store.

Versioned user / agent / project entries live under the product data
``knowledge/`` directory. This is not a checkpointer table, not git, not
``.scratch/``, and not a retrieval index; query-time retrieval derives a per-run vector store.
"""
