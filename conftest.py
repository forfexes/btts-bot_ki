"""pytest support for the script-style regression tests.

test_netrattler_regression_step1 / stability_step2 / stability_step3 take
``bot``, ``builder``, ``ml`` and ``src`` module objects and are normally run
as ``python test_x.py``. These fixtures load the same modules so pytest can run
them too. ``test_netrattler_core.py`` is a pure script (module-level asserts
run on import and depend on a clean environment), so pytest skips collecting it.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
collect_ignore = ["test_netrattler_core.py"]


@pytest.fixture(autouse=True)
def _restore_requests():
    """Loading btts_bot patches requests; never leak that into other tests."""
    import requests
    saved = (requests.get, requests.post, requests.sessions.Session.request,
             requests.Session.send if hasattr(requests.Session, "send") else None)
    yield
    requests.get, requests.post = saved[0], saved[1]
    requests.sessions.Session.request = saved[2]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bot():
    return _load("conftest_btts_bot", "btts_bot.py")


@pytest.fixture
def builder():
    return _load("conftest_builder", "netrattler_builder_engine.py")


@pytest.fixture
def ml():
    return _load("netrattler_ml_player", "netrattler_ml_player.py")


@pytest.fixture
def src():
    return _load("conftest_prop_sources", "netrattler_prop_sources.py")
