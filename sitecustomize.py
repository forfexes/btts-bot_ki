# Loaded automatically when the repo is on PYTHONPATH (GitHub workflows). No-op unless routing env is set.
try:
    import netrattler_table_router as _ntr_router
    _ntr_router.install()
except Exception:
    pass
try:
    import netrattler_odds_api_budget as _ntr_budget
    _ntr_budget.install()
except Exception:
    pass
