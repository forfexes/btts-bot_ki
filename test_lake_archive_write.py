"""Lake rows go to the archive DSN with retention; never to the main project by default."""
import sys, types, unittest, os
import netrattler_all_source_harvester as h

class FakeCur:
    def __init__(self, log): self.log = log
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, args=None): self.log.append(("exec", sql, args))

class FakeConn:
    def __init__(self, log): self.log = log
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return FakeCur(self.log)
    def commit(self): self.log.append(("commit",))

class T(unittest.TestCase):
    def setUp(self):
        self.log = []
        pg = types.ModuleType("psycopg2"); pg.connect = lambda dsn, connect_timeout=20: FakeConn(self.log)
        ex = types.ModuleType("psycopg2.extras")
        ex.Json = lambda v: ("json", v)
        def execute_values(cur, sql, vals, template=None): self.log.append(("values", sql, len(vals), template))
        ex.execute_values = execute_values
        pg.extras = ex
        sys.modules["psycopg2"] = pg; sys.modules["psycopg2.extras"] = ex

    def test_archive_insert_and_retention(self):
        rows = [h.data_lake_row("S", "t", "e", {"a": 1}, entity_name="x")]
        ok, fail = h.lake_insert_pg("postgresql://x", rows, 5)
        self.assertEqual((ok, fail), (1, 0))
        kinds = [x[0] for x in self.log]
        self.assertIn("values", kinds); self.assertIn("commit", kinds)
        self.assertTrue(any(x[0] == "exec" and "delete from netrattler_data_lake_raw" in x[1] and x[2] == (5,) for x in self.log))
        self.assertTrue(any("on conflict (data_hash) do nothing" in x[1] for x in self.log if x[0] == "values"))

    def test_no_main_fallback_by_default(self):
        called = []
        orig = h.sb_insert
        h.sb_insert = lambda *a, **k: called.append(1) or (0, 0)
        os.environ.pop("DATA_LAKE_DSN", None); os.environ.pop("DATA_LAKE_MAIN_FALLBACK", None)
        try:
            h.push_lake([h.data_lake_row("S", "t", "e", {"a": 1})])
        finally:
            h.sb_insert = orig
        self.assertEqual(called, [])

if __name__ == "__main__":
    unittest.main()
