"""Shared Chat surface backed by the embedded Deep Agents harness.

Deep Agents owns model/tool iteration; the application persists transcripts
and native interrupts in application.sqlite and surfaces them through Chat.
Filesystem tools target project storage. History is not the
working project.
"""
