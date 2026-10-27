import sys, types
for _m in ("psycopg2", "psycopg2.extras"):
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            sys.modules[_m] = types.SimpleNamespace(connect=None, extras=None, execute_values=None, Json=None)
import psycopg2
if not hasattr(sys.modules["psycopg2.extras"], "Json"):
    sys.modules["psycopg2.extras"].Json = None
import netrattler_odds_archive as a


def test_is_alt_only_odd_lines():
    assert a.is_alt("totals_3_75") and a.is_alt("totals_ht_0_75")
    assert not a.is_alt("totals_2_5") and not a.is_alt("totals_ht_1_5") and not a.is_alt("totals_btts")


def test_prune_source_has_safety_gates():
    import inspect
    src = inspect.getsource(a.prune_verified)
    assert "n_arch >= n_main" in src and "lt.{today}" in src or "captured_date.lt.{today}" in src
    assert "last_d = d" in src  # kein Endlosloop auf Standard-Maerkten
