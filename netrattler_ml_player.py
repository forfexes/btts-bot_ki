"""
NETRATTLER — Player-Prop XGBoost Predictor
==========================================

Verdrahtet die 18 trainierten Player-Prop-Modelle (player_shots_*, player_sot_*,
player_goal_*, player_assist_*, player_passes_*, player_tackles_*,
player_fouls_*, player_card_*, player_corners_*) aus Supabase `ml_models`
in den Prop-Builder.

Ziel: echte Modell-Wahrscheinlichkeit pro Player-Prop statt implied-odds.
Damit bekommt der Builder eine ECHTE Edge (Modell vs. Buchmacher), nicht nur
die vig-getriebene Naeherung.

Fehlertolerant: laedt Modelle lazy + gecacht; scheitert etwas, wird None
zurueckgegeben und der Builder faellt auf die implied-odds-Wahrscheinlichkeit
zurueck. Kann den Lauf nie brechen.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import math

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


# Reihenfolge MUSS exakt dem Training entsprechen (train_model.PLAYER_FEATURE_COLS).
PLAYER_FEATURE_COLS = [
    "games_prior", "avg_minutes", "avg_shots", "avg_sot", "avg_goals", "avg_assists",
    "avg_passes", "avg_tackles", "avg_fouls_committed", "avg_fouls_won",
    "avg_cards", "avg_corners", "avg_source_count",
    "elo_diff", "opponent_elo", "is_home", "is_favorite",
]

# category -> {line: model_name}. Nur real trainierte Modelle.
_LINE_MODELS: Dict[str, Dict[float, str]] = {
    "shots":             {0.5: "player_shots_over05_model", 1.5: "player_shots_over15_model", 2.5: "player_shots_over25_model"},
    "sot":               {0.5: "player_sot_over05_model", 1.5: "player_sot_over15_model"},
    "sot_outside_box":   {0.5: "player_sot_over05_model"},
    "score":             {0.5: "player_goal_over05_model"},
    "first_scorer":      {0.5: "player_goal_over05_model"},
    "last_scorer":       {0.5: "player_goal_over05_model"},
    "assist":            {0.5: "player_assist_over05_model"},
    "passes":            {24.5: "player_passes_over245_model", 34.5: "player_passes_over345_model", 44.5: "player_passes_over445_model"},
    "tackles_committed": {0.5: "player_tackles_over05_model", 1.5: "player_tackles_over15_model"},
    "tackles_received":  {0.5: "player_tackles_over05_model", 1.5: "player_tackles_over15_model"},
    "fouls":             {0.5: "player_fouls_committed_over05_model", 1.5: "player_fouls_committed_over15_model"},
    "fouls_won":         {0.5: "player_fouls_won_over05_model", 1.5: "player_fouls_won_over15_model"},
    "yellow_cards":      {0.5: "player_card_over05_model"},
    "corners":           {0.5: "player_corners_over05_model"},
}

_ALL_PLAYER_MODELS = sorted({m for tbl in _LINE_MODELS.values() for m in tbl.values()})

_MODEL_CACHE: Dict[str, Any] = {}
_LOADED = False
_LAST_LOAD_ERROR = ""


def model_for(category: str, line: float) -> Optional[str]:
    """Waehlt das Modell fuer Kategorie + naechstliegende trainierte Linie."""
    table = _LINE_MODELS.get(category)
    if not table:
        return None
    try:
        target = float(line if line is not None else 0.5)
    except (TypeError, ValueError):
        target = 0.5
    best = min(table.keys(), key=lambda L: abs(L - target))
    return table[best]


def build_player_features(avg_stats: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> List[float]:
    """Baut den 17er-Feature-Vektor: Spieler-Schnitte + Rollen-Kontext."""
    ctx = context or {}
    def cval(key: str, default: float = 0.0) -> float:
        try:
            return float(ctx.get(key, default) or default)
        except (TypeError, ValueError):
            return default
    def val(*keys: str) -> float:
        for k in keys:
            row = avg_stats.get(k)
            if row and row.get("avg") is not None:
                try:
                    return float(row["avg"])
                except (TypeError, ValueError):
                    continue
        return 0.0

    def games() -> float:
        for row in avg_stats.values():
            g = (row or {}).get("games")
            if g:
                try:
                    return float(g)
                except (TypeError, ValueError):
                    continue
        return 0.0

    g = games()
    return [
        g,                                    # games_prior
        val("minutes"),                       # avg_minutes
        val("shots"),                         # avg_shots
        val("sot", "shots_on_target"),        # avg_sot
        val("goals"),                         # avg_goals
        val("assists"),                       # avg_assists
        val("passes"),                        # avg_passes
        val("tackles"),                       # avg_tackles
        val("fouls_committed", "fouls"),      # avg_fouls_committed
        val("fouls_won"),                     # avg_fouls_won
        val("cards", "yellow_cards"),         # avg_cards
        val("corners"),                       # avg_corners
        g,                                    # avg_source_count (Proxy: games)
        cval("elo_diff"),                     # elo_diff
        cval("opponent_elo", 1500.0),         # opponent_elo
        cval("is_home"),                      # is_home
        cval("is_favorite"),                  # is_favorite
    ]


def load_player_models(
    supabase_url: str,
    supabase_key: str,
    timeout: int = 20,
    model_names: Optional[List[str]] = None,
    batch_size: int = 3,
    force: bool = False,
) -> int:
    """Load player models incrementally from Supabase with per-model fallback.

    STEP3 hardening:
    - only required blobs are requested;
    - small batched ``in.(...)`` requests are attempted first;
    - if a batch times out, returns no rows, or misses one model, each missing
      model is retried with ``eq.<model_name>``;
    - successful partial loads stay cached;
    - one failed request never poisons the whole process with models=0.
    """
    global _LOADED, _LAST_LOAD_ERROR
    if not supabase_url or not supabase_key or requests is None:
        _LAST_LOAD_ERROR = "missing Supabase credentials or requests"
        return len(_MODEL_CACHE)

    wanted = list(dict.fromkeys(model_names or _ALL_PLAYER_MODELS))
    wanted = [name for name in wanted if name in _ALL_PLAYER_MODELS]
    if not wanted:
        return len(_MODEL_CACHE)

    if force:
        for name in wanted:
            _MODEL_CACHE.pop(name, None)

    missing = [name for name in wanted if name not in _MODEL_CACHE]
    if not missing:
        _LOADED = all(name in _MODEL_CACHE for name in _ALL_PLAYER_MODELS)
        _LAST_LOAD_ERROR = ""
        return len(_MODEL_CACHE)

    try:
        batch_size = max(1, min(5, int(batch_size or 3)))
    except Exception:
        batch_size = 3
    try:
        timeout = max(10, int(timeout or 20))
    except Exception:
        timeout = 20

    import pickle, base64, io
    errors: List[str] = []

    def _decode_rows(rows: List[Dict[str, Any]], allowed: set[str]) -> set[str]:
        loaded: set[str] = set()
        for row in rows or []:
            name = str(row.get("model_name") or "")
            data = row.get("model_data") or ""
            if name not in allowed or not data:
                continue
            try:
                obj = pickle.load(io.BytesIO(base64.b64decode(data)))
                model = obj.get("model") if isinstance(obj, dict) else obj
                if model is not None:
                    _MODEL_CACHE[name] = model
                    loaded.add(name)
            except Exception as exc:
                errors.append(f"{name} unpickle {type(exc).__name__}: {str(exc)[:80]}")
        return loaded

    def _request(params: Dict[str, str], req_timeout: int):
        return requests.get(
            f"{supabase_url}/rest/v1/ml_models",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            params=params,
            timeout=req_timeout,
        )

    for start in range(0, len(missing), batch_size):
        chunk = missing[start:start + batch_size]
        allowed = set(chunk)
        loaded_here: set[str] = set()

        # Fast path: one request for a small batch.
        try:
            names = ",".join(chunk)
            r = _request({
                "select": "model_name,model_data",
                "model_name": f"in.({names})",
                "limit": str(len(chunk)),
            }, timeout)
            if r.ok:
                try:
                    loaded_here |= _decode_rows(r.json() or [], allowed)
                except Exception as exc:
                    errors.append(f"{chunk[0]}.. bad json: {str(exc)[:90]}")
            else:
                errors.append(f"{chunk[0]}.. HTTP {r.status_code}: {str(getattr(r, 'text', ''))[:90]}")
        except Exception as exc:
            errors.append(f"{chunk[0]}.. request {type(exc).__name__}: {str(exc)[:90]}")

        # Robust fallback: retry each missing model by exact name.  This also
        # handles Supabase/PostgREST deployments where a large base64 batch is
        # slow even though single-row downloads work.
        still_missing = [name for name in chunk if name not in loaded_here and name not in _MODEL_CACHE]
        for name in still_missing:
            try:
                r = _request({
                    "select": "model_name,model_data",
                    "model_name": f"eq.{name}",
                    "limit": "1",
                }, max(timeout, 25))
                if not r.ok:
                    errors.append(f"{name} HTTP {r.status_code}: {str(getattr(r, 'text', ''))[:90]}")
                    continue
                try:
                    got = _decode_rows(r.json() or [], {name})
                except Exception as exc:
                    errors.append(f"{name} bad json: {str(exc)[:90]}")
                    got = set()
                if name not in got:
                    errors.append(f"{name} not returned")
            except Exception as exc:
                errors.append(f"{name} request {type(exc).__name__}: {str(exc)[:90]}")

    _LOADED = all(name in _MODEL_CACHE for name in _ALL_PLAYER_MODELS)
    unresolved = [name for name in wanted if name not in _MODEL_CACHE]
    if unresolved:
        errors.append("unresolved=" + ",".join(unresolved[:8]))
    _LAST_LOAD_ERROR = "; ".join(errors)[:1200]
    if not unresolved:
        _LAST_LOAD_ERROR = ""
    return len(_MODEL_CACHE)

def player_model_load_status() -> Dict[str, Any]:
    return {
        "loaded": len(_MODEL_CACHE),
        "complete": bool(_LOADED),
        "error": _LAST_LOAD_ERROR,
        "models": sorted(_MODEL_CACHE.keys()),
    }


def predict_player_prop(
    avg_stats: Dict[str, Any], category: str, line: float,
    context: Optional[Dict[str, Any]] = None
) -> Optional[float]:
    """Gibt die Modell-Wahrscheinlichkeit (0..1) fuer 'Over line' zurueck oder None.
    context = {elo_diff, opponent_elo, is_home, is_favorite} fuer das Rollen-Feature."""
    if not avg_stats or not _MODEL_CACHE:
        return None
    name = model_for(category, line)
    if not name or name not in _MODEL_CACHE:
        return None
    try:
        feats = build_player_features(avg_stats, context)
        # Ohne Spielhistorie keine sinnvolle Vorhersage.
        if feats[0] <= 0:
            return None
        model = _MODEL_CACHE[name]
        prob = float(model.predict_proba([feats])[0][1])
        return max(0.02, min(0.98, prob))
    except Exception:
        return None



def empirical_player_prop_probability(avg_stats: Dict[str, Any], category: str, line: float) -> Optional[float]:
    """History-backed Poisson probability for an observed player-prop line.

    This is an independent statistical model built from the player's stored
    per-match averages. It is used as a fallback/calibration signal when the
    trained classifier is missing or clearly under-confident. No bookmaker
    implied probability is used. A small category prior is blended in so tiny
    samples do not create unrealistic 80-90% probabilities.
    """
    if not avg_stats:
        return None
    key_map = {
        "shots": ("shots",),
        "sot": ("sot", "shots_on_target"),
        "sot_outside_box": ("sot", "shots_on_target"),
        "score": ("goals",),
        "first_scorer": ("goals",),
        "last_scorer": ("goals",),
        "assist": ("assists",),
        "passes": ("passes",),
        "tackles": ("tackles",),
        "tackles_committed": ("tackles",),
        "tackles_received": ("tackles_received", "tackles"),
        "fouls": ("fouls_committed", "fouls"),
        "fouls_committed": ("fouls_committed", "fouls"),
        "fouls_won": ("fouls_won",),
        "yellow_cards": ("yellow_cards", "cards"),
        "cards": ("yellow_cards", "cards"),
        "saves": ("saves",),
        "offsides": ("offsides",),
    }
    priors = {
        "shots": 1.8, "sot": 0.75, "sot_outside_box": 0.20,
        "score": 0.28, "first_scorer": 0.28, "last_scorer": 0.28,
        "assist": 0.18, "passes": 28.0,
        "tackles": 1.6, "tackles_committed": 1.6, "tackles_received": 1.4,
        "fouls": 1.35, "fouls_committed": 1.35, "fouls_won": 1.25,
        "yellow_cards": 0.22, "cards": 0.22, "saves": 2.2, "offsides": 0.45,
    }
    row = None
    for key in key_map.get(category, (category,)):
        cand = avg_stats.get(key)
        if cand and cand.get("avg") is not None:
            row = cand
            break
    if not row:
        return None
    try:
        avg = float(row.get("avg") or 0)
        games = max(0.0, float(row.get("games") or 0))
        ln = float(line if line is not None else 0.5)
    except (TypeError, ValueError):
        return None
    if avg <= 0 or games <= 0:
        return None

    # 2+ may arrive as line=2 while Over 1.5 arrives as line=1.5.
    if ln <= 0.5:
        need = 1
    elif abs(ln - round(ln)) < 1e-6:
        need = max(1, int(round(ln)))
    else:
        need = max(1, int(math.floor(ln)) + 1)

    prior = float(priors.get(category, max(0.15, min(avg, 2.0))))
    prior_games = 5.0
    lam = (avg * games + prior * prior_games) / (games + prior_games)
    lam = max(0.01, min(lam, 60.0))

    # Poisson survival P(X >= need). For very large pass lines, use a normal
    # approximation to avoid long factorial sums.
    if need > 15:
        sd = max(1.0, math.sqrt(lam))
        z = ((need - 0.5) - lam) / sd
        prob = 0.5 * math.erfc(z / math.sqrt(2.0))
    else:
        cdf = 0.0
        term = math.exp(-lam)
        cdf += term
        for k in range(1, need):
            term *= lam / k
            cdf += term
        prob = 1.0 - cdf

    # Mild sample-size confidence haircut; large samples are nearly untouched.
    confidence = min(1.0, games / 10.0)
    neutral = 0.50 if need <= 2 else 0.35
    prob = neutral * (1.0 - confidence) + prob * confidence
    return max(0.03, min(0.95, float(prob)))

def loaded_model_count() -> int:
    return len(_MODEL_CACHE)


# Kandidaten-Linien pro Kategorie (hoch → niedrig), inkl. abgeleiteter 3+/2+.
_LINE_LADDER: Dict[str, list] = {
    "shots":             [2.5, 1.5, 0.5],
    "sot":               [1.5, 0.5],
    "sot_outside_box":   [0.5],
    "tackles_committed": [1.5, 0.5],
    "tackles_received":  [1.5, 0.5],
    "tackles":           [1.5, 0.5],
    "fouls":             [1.5, 0.5],
    "fouls_committed":   [1.5, 0.5],
    "fouls_won":         [1.5, 0.5],
    "score":             [0.5],
    "assist":            [0.5],
    "passes":            [44.5, 34.5, 24.5],
    "cards":             [0.5],
    "yellow_cards":      [0.5],
    "corners":           [0.5],
}


def best_line_for_role(
    avg_stats: Dict[str, Any], category: str,
    context: Optional[Dict[str, Any]] = None,
    min_conf: float = 0.55,
) -> Optional[Tuple[float, float]]:
    """
    Waehlt die HOECHSTE Linie, die das Modell noch mit >= min_conf deckt.
    Ergibt Nates Staffelung datengetrieben: dominanter Favorit-Angreifer -> 2+/3+,
    solider -> 2+, schwaecherer rollenpassender -> 1+.
    Rueckgabe: (line, probability) oder None, wenn keine Linie sicher genug ist.
    """
    lines = _LINE_LADDER.get(category)
    if not lines:
        return None
    for ln in lines:                      # hoch -> niedrig
        prob = predict_player_prop(avg_stats, category, ln, context)
        if prob is not None and prob >= min_conf:
            return (ln, prob)
    # Keine Linie ueber Schwelle: niedrigste Linie mit ihrer Prob zurueckgeben,
    # damit der Aufrufer selbst entscheiden kann (oder None bei zu schwach).
    lowest = lines[-1]
    prob = predict_player_prop(avg_stats, category, lowest, context)
    if prob is not None and prob >= (min_conf - 0.10):
        return (lowest, prob)
    return None


__all__ = [
    "PLAYER_FEATURE_COLS", "load_player_models", "predict_player_prop",
    "build_player_features", "model_for", "loaded_model_count",
    "empirical_player_prop_probability",
]
