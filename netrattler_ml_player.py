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

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


# Reihenfolge MUSS exakt dem Training entsprechen (train_model.PLAYER_FEATURE_COLS).
PLAYER_FEATURE_COLS = [
    "games_prior", "avg_minutes", "avg_shots", "avg_sot", "avg_goals", "avg_assists",
    "avg_passes", "avg_tackles", "avg_fouls_committed", "avg_fouls_won",
    "avg_cards", "avg_corners", "avg_source_count",
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


def build_player_features(avg_stats: Dict[str, Any]) -> List[float]:
    """Baut den 13er-Feature-Vektor aus get_supabase_player_avg_stats()-Output."""
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
    ]


def load_player_models(supabase_url: str, supabase_key: str, timeout: int = 60) -> int:
    """Laedt die 18 Player-Modelle gefiltert aus ml_models. Idempotent + gecacht."""
    global _LOADED
    if _LOADED:
        return len(_MODEL_CACHE)
    _LOADED = True
    if not supabase_url or not supabase_key or requests is None:
        return 0
    try:
        import pickle, base64, io
        names = ",".join(_ALL_PLAYER_MODELS)
        r = requests.get(
            f"{supabase_url}/rest/v1/ml_models",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            params={"select": "model_name,model_data", "model_name": f"in.({names})"},
            timeout=timeout,
        )
        if not r.ok:
            return 0
        for row in r.json():
            name = row.get("model_name", "")
            data = row.get("model_data", "")
            if not name or not data:
                continue
            try:
                obj = pickle.load(io.BytesIO(base64.b64decode(data)))
                _MODEL_CACHE[name] = obj["model"]
            except Exception:
                continue
    except Exception:
        return 0
    return len(_MODEL_CACHE)


def predict_player_prop(
    avg_stats: Dict[str, Any], category: str, line: float
) -> Optional[float]:
    """Gibt die Modell-Wahrscheinlichkeit (0..1) fuer 'Over line' zurueck oder None."""
    if not avg_stats or not _MODEL_CACHE:
        return None
    name = model_for(category, line)
    if not name or name not in _MODEL_CACHE:
        return None
    try:
        feats = build_player_features(avg_stats)
        # Ohne Spielhistorie keine sinnvolle Vorhersage.
        if feats[0] <= 0:
            return None
        model = _MODEL_CACHE[name]
        prob = float(model.predict_proba([feats])[0][1])
        return max(0.02, min(0.98, prob))
    except Exception:
        return None


def loaded_model_count() -> int:
    return len(_MODEL_CACHE)


__all__ = [
    "PLAYER_FEATURE_COLS", "load_player_models", "predict_player_prop",
    "build_player_features", "model_for", "loaded_model_count",
]
