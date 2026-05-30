"""Regression: the prediction-engine factory must build exactly once under
concurrent first-calls.

The web app fires ``/predictions/check``, ``/predictions/case`` and
``/predictions/generate`` almost simultaneously; each is resolved on its own
threadpool thread and calls ``_cached_prediction_engine``. The previous
``functools.lru_cache`` implementation did not hold its lock across the wrapped
build, so the threads raced ChromaDB's non-thread-safe ``PersistentClient``
construction, corrupting its shared state ("'RustBindingsAPI' object has no
attribute 'bindings'" / "Could not connect to tenant default_tenant") and
leaving RAG silently unavailable in production.
"""

import threading
import time

import apps.api.src.dependencies as deps


def test_cached_prediction_engine_builds_once_under_concurrency(monkeypatch):
    deps._prediction_engine_singleton = None
    build_count: list[int] = []
    count_lock = threading.Lock()

    def slow_build():
        with count_lock:
            build_count.append(1)
        time.sleep(0.1)  # widen the window so unsynchronised callers would overlap
        return object()

    monkeypatch.setattr(deps, "_build_prediction_engine", slow_build)

    results: list[object] = []
    results_lock = threading.Lock()

    def call():
        engine = deps._cached_prediction_engine()
        with results_lock:
            results.append(engine)

    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert len(build_count) == 1, f"engine built {len(build_count)}x (race not serialised)"
        assert len({id(r) for r in results}) == 1, "threads received different engine instances"
    finally:
        deps._prediction_engine_singleton = None
