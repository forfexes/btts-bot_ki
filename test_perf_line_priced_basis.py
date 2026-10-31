import re, ast
src = open('btts_bot.py', encoding='utf-8').read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_ntr_perf_line')
ns = {'_ntr_float': lambda x, d=0.0: float(x) if x is not None else d}
exec(compile(ast.Module([fn], []), 'x', 'exec'), ns)
f = ns['_ntr_perf_line']

def test_unpriced_shows_na():
    assert 'n/a' in f({'bets': 40, 'priced': 0, 'wins': 10, 'losses': 30, 'roi': 0, 'profit': 0}, '7 Tage')

def test_partial_basis_shown():
    assert 'Basis 10/40' in f({'bets': 40, 'priced': 10, 'wins': 10, 'losses': 30, 'roi': 5.0, 'profit': 1.0}, 'Monat')

def test_full_basis_plain():
    assert 'Basis' not in f({'bets': 10, 'priced': 10, 'wins': 5, 'losses': 5, 'roi': 5.0, 'profit': 1.0}, 'Monat')
