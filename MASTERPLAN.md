# NETRATTLER MASTERPLAN
> Zuletzt aktualisiert: 2026-06-27
> Bot-Version: V11 Football

---

## 📁 REPO-STRUKTUR

```
forfexes/btts-bot_ki/
├── btts_bot.py              # Haupt-Bot (~22.000 Zeilen)
├── prop_builder_v4.py       # Standalone Prop Builder (Pinnacle Specials)
├── settlement.py            # ⚠️ FALSCH — Kopie von scrape_player_stats.py!
├── scrape_player_stats.py   # Player Stats Scraper (StatsBomb/SofaScore/FBref)
├── train_model.py           # XGBoost ML-Training (wöchentlich)
├── supabase_v4.py           # Supabase Helper-Klasse
├── player_identity.py       # looks_like_player(), extract_player_from_description()
├── prop_value_engine.py     # Edge/Value Berechnungen
├── requirements.txt         # Python Dependencies
├── MASTERPLAN.md            # Dieses Dokument
└── .github/workflows/
    ├── btts_tips.yml        # Haupt-Bot (4x täglich: 06:30/12:30/18:30/21:30 UTC)
    ├── btts-settlement.yml  # Settlement (alle 3h) ⚠️ ruft falsches script auf
    ├── scrape_player_stats.yml  # Player Stats (täglich 04:10 UTC)
    ├── train_model.yml      # ML Training (montags 04:00 UTC)
    ├── cleanup.yml          # GitHub Runs cleanup (täglich 03:00 UTC)
    └── telegram_test.yml    # Telegram Test (manuell)
```

---

## 🗄️ SUPABASE TABELLEN

| Tabelle | Status | Zweck |
|---------|--------|-------|
| `tips` | ✅ existiert | Alle gesendeten Tipps + Settlement |
| `player_match_stats` | ✅ neu erstellt | Rohdaten pro Spiel pro Spieler |
| `player_avg_stats` | ✅ neu erstellt | Durchschnitte + Hit Rates |
| `player_prop_db` | ✅ existiert | Pinnacle Player Props |
| `prop_picks` | ✅ existiert | Gesendete Prop Builder Picks |
| `source_health` | ✅ neu erstellt | Scraper Status |
| `ml_models` | ✅ existiert | Trainierte XGBoost Modelle |
| `ml_tips` | ✅ existiert | ML Feedback Loop |
| `bankroll_state` | ✅ existiert | Drawdown Protection |
| `clv_tracking` | ✅ existiert | Closing Line Value |

---

## ✅ MODULE — STATUS

### FERTIG
- [x] **Pinnacle Scraper** — Matchups + Player Props (kostenlos, Guest API)
- [x] **BTTS/Over/Combo/HT Analyse** — via Gemini + Groq + OpenRouter
- [x] **Prop Builder** — Nate Ladder, GodTipsterr, Aystar Booking, Multi-Market, Category
- [x] **Settlement** — SofaScore + AllSports + API-Football + Football-Data (via Teamname-Match)
- [x] **Multi-Combo System** — 3-11 Legs automatisch
- [x] **XGBoost ML** — Training wöchentlich, Inference im Bot
- [x] **Drawdown Protection** — Normal/Conservative/Strict/Paused Mode
- [x] **CLV Tracking** — Opening vs Closing Line
- [x] **Bankroll Tracker** — Units + ROI + Streak
- [x] **StatsBomb Hit Rates** — WM22, Euro24, Copa24 (Supabase Cache)
- [x] **TSA Key Rotation** — TheStatsAPI Multi-Key mit Auto-Fallback
- [x] **PROP_SCORE System** — Leg Quality Scoring 0-100
- [x] **looks_like_player()** — Generische Namen filtern
- [x] **Player Stats Scraper** — StatsBomb + SofaScore + FBref → Supabase
- [x] **Auto League Switch** — Performance-basierte Liga-Rotation

### IN ARBEIT / UNVOLLSTÄNDIG
- [ ] **settlement.py** — Falsches File! Muss echtes Settlement-Script werden
- [ ] **Player DB Splits** — Nur Saison-Durchschnitt, fehlt: last3/5/10/20, Heim/Auswärts
- [ ] **Referee Database** — Code-Stubs vorhanden, keine echte Supabase-Tabelle
- [ ] **Lineup Engine** — SofaScore-Lineups werden geholt, nicht persistent gespeichert

### NOCH NICHT GEBAUT
- [ ] **Fixture-ID-System** — Settlement matcht per Teamname (fehleranfällig)
- [ ] **Understat xG/xA Scraper** — Nur im Bot inline, kein dedicated Scraper
- [ ] **Transfermarkt Verletzungen** — Scraping-Stub vorhanden, nicht zuverlässig
- [ ] **Community Intelligence** — Twitter/Reddit/Telegram Scraping (0%)
- [ ] **Performance Dashboard** — ROI/Yield/Hit Rate je Markt/Liga/Schiri (Supabase da, kein UI)
- [ ] **Auto ML-Retraining nach Settlement** — Läuft nur wöchentlich, nicht settlement-triggered

---

## 🔑 GITHUB SECRETS

| Secret | Zweck |
|--------|-------|
| `SUPABASE_URL` | Supabase Projekt URL |
| `SUPABASE_KEY` | **Service Role Key** (Legacy JWT, beginnt mit eyJ...) |
| `GEMINI_API_KEYS` | Komma-getrennt, mehrere Keys |
| `GROQ_API_KEYS` | Komma-getrennt |
| `ODDS_API_KEYS` | The Odds API Keys |
| `FOOTBALL_DATA_API_KEYS` | football-data.org Keys |
| `THESTATSAPI_KEY` | TheStatsAPI Key(s) |
| `TELEGRAM_TOKEN` | Bot Token |
| `TELEGRAM_CHAT_ID` | Haupt-Chat |
| `TELEGRAM_GROUP_BTTS` | BTTS Kanal |
| `TELEGRAM_GROUP_OVER25` | Over 2.5 Kanal |
| `TELEGRAM_GROUP_COMBO` | Combo Kanal |
| `TELEGRAM_GROUP_COMBOS` | Multi-Combo Kanal |
| `TELEGRAM_GROUP_BTTS_HT` | HT Kanal |
| `TELEGRAM_GROUP_HZ_LIVE` | Live HZ Kanal |
| `TELEGRAM_GROUP_LATE_GOALS` | Late Goals Kanal |
| `TELEGRAM_GROUP_STATS` | Stats/Props Kanal |
| `TELEGRAM_GROUP_ADVANCED_PROPS` | Props Kanal |

---

## 🚀 ROADMAP (Priorität)

### PRIO 1 — Sofort (Bugs/Broken)
1. **settlement.py fixen** — Echtes Settlement-Script schreiben das `btts-settlement.yml` aufruft
2. **Fixture-ID-System** — Match-IDs statt Teamnamen für Settlement

### PRIO 2 — Kurzfristig (nächste 1-2 Wochen)
3. **Player DB Splits** — last3/5/10/20 + Heim/Auswärts in `scrape_player_stats.py`
4. **Understat xG/xA Scraper** — Dedicated Script, täglich
5. **Referee Database** — Supabase Tabelle + Scraper

### PRIO 3 — Mittelfristig
6. **Lineup Engine** — Persistent in Supabase, Settlement-Integration
7. **Transfermarkt** — Verletzungen/Sperren zuverlässig
8. **Performance Dashboard** — Telegram-basiert oder Web-UI

### PRIO 4 — Langfristig
9. **Community Intelligence** — Twitter/Reddit Scraping
10. **Auto ML-Retraining** — Nach jedem Settlement triggern

---

## ⚠️ BEKANNTE PROBLEME

| Problem | Status | Fix |
|---------|--------|-----|
| `settlement.py` = Kopie von scrape_player_stats | 🔴 offen | Echtes Script schreiben |
| SofaScore blockt GitHub IPs (403) | 🟡 bekannt | Playwright Fallback, oder via Proxy |
| FBref blockt GitHub IPs (403) | 🟡 bekannt | 7s Rate Limit + Playwright |
| StatsBomb HR nur WM22/Euro24/Copa24 | 🟡 bekannt | Supabase Cache via scrape_player_stats |
| Settlement matcht per Teamname (unzuverlässig) | 🔴 offen | Fixture-ID-System |
| API_FOOTBALL suspended | ✅ deaktiviert | Kein Fix nötig |

---

## 📊 DATENQUELLEN

| Quelle | Zweck | Status |
|--------|-------|--------|
| Pinnacle Guest API | Quoten + Player Props | ✅ stabil |
| StatsBomb Open Data | Hit Rates (WM/Euro/Copa) | ✅ stabil |
| SofaScore | Fixtures + Lineups + Form | 🟡 GitHub-Block |
| FBref | Saison-Stats | 🟡 GitHub-Block |
| FotMob | xG + Fixtures | ✅ stabil |
| martj42 (GitHub) | Länderspiel-Historie | ✅ stabil |
| ClubElo | Team Elo-Ratings | ✅ stabil |
| OpenLigaDB | Deutsche Ligen | ✅ stabil |
| TheSportsDB | Fixtures (free key) | ✅ stabil |
| ESPN | Fixtures + Settlement | ✅ stabil |
| Football-Data.co.uk | Historische Stats | ✅ stabil |
| The Odds API | Quoten (kostenpflichtig) | ✅ stabil |
| Understat | xG/xA | 🟡 GitHub-Block |
| Forebet | Predictions | 🟡 blockiert |
| Transfermarkt | Verletzungen | 🟡 blockiert |
| ScoutingStats | Props | 🟡 instabil |
| Oddspedia | Props | 🟡 Cloudflare |

---

## 💡 TECHNISCHE ENTSCHEIDUNGEN

- **Keine API-Football** — Account suspended, deaktiviert
- **Supabase** — Alle Daten, Settlement, ML-Modelle
- **GitHub Actions** — 4 Bot-Runs täglich + Settlement alle 3h
- **Gemini** → **Groq** → **OpenRouter** — AI Fallback-Kette
- **Playwright** — Für blockierte Sites (SofaScore, FBref)
- **Pinnacle Guest API** — Kostenlose Sharp Quoten
- **XGBoost** — Primäres ML-Modell, kalibriert via CalibratedClassifierCV
