"""Deterministic auto-grounding pipeline for LLM-assisted gold labeling.

Modules in this package are pure: no LLM calls, no I/O beyond explicit
artifact writers. The dual-LLM dispatcher and CLI live in ``runner.py``
and the ``scripts/eval/auto_label.py`` / ``scripts/eval/adjudicate.py``
entry points respectively.
"""
