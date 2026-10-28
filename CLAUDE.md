# NETRATTLER (btts-bot_ki) – Projektnotizen für jede neue Sitzung

## Regeln des Besitzers
- Nur kostenlose Datenquellen/APIs. Nichts Bezahltes, kein Scraping gegen Nutzungsbedingungen.
- Keys/Secrets nie im Chat anzeigen oder erfragen: sie gehören in GitHub-Secrets (Name nennen, Wert nie).
- Direkt handeln, prüfen, committen, pushen (main). Einzelne Dateien statt Zips.
- Vor dem Löschen von Produktionsdaten verifizieren (archiviert/kopiert).
- Sprache: Deutsch (Schweiz).
- Altes Handover (Oktober): REAL_ODDS_ONLY, keine künstlichen Tipps nur um Gruppen zu füllen, Qualität vor Quantität, 0 Picks sind akzeptabel, keine Quellennamen in sichtbaren Tipps. Einzige Ausnahme laut Besitzer (2026-10-28): Modell-Builder ohne Buchmacherquote, klar als faire Modellquote gekennzeichnet.

## Betrieb
- Läuft auf GitHub Actions (Repo forfexes/btts-bot_ki). Workflows per REST starten:
  `gh api -X POST repos/forfexes/btts-bot_ki/actions/workflows/<datei>/dispatches -f ref=main`
  (`gh workflow run` scheitert an GraphQL 403). Logs sind nicht lesbar -> Ergebnisse über Tabelle `netrattler_card_diag` (Spalte `info` jsonb, Feld `probe`).
- Wichtige Workflows: `btts_tips.yml` (Tipp-Run), `netrattler_settlement_v16_final.yml` (Auswertung), `netrattler_apifootball_players.yml` (täglich, Spielerstatistik inkl. Tackles), `netrattler_odds_archive.yml`, Proben `netrattler_*_probe.yml`.
- CI: `netrattler_ci.yml` (neue Tests dort eintragen).

## Datenbanken (Supabase, je <500 MB, Free)
- MAIN "NETRATTLER Project" (sugycqnjncgfheueqaee): tips, netrattler_builder_picks, player_game_log, apif_player_match, netrattler_card_diag.
- V4 (alhsljynycapnikeqrcy): Odds-Archiv (direkt per V4_DATABASE_URL).
- V2: player_match_stats + netrattler_match_history, per Router `netrattler_table_router.py` (sitecustomize.py, NETRATTLER_ROUTE_TABLES) von MAIN umgeleitet. V3: odds_history-Kopie. MCP erreicht nur MAIN und V4.
- `player_game_log` NICHT routen (war leer in V2).

## Builder
- Engine `netrattler_builder_engine.py`, Stile `netrattler_builder_styles.py`; nur echte Buchmacherquoten (`is_bookmaker_source`), Quoten >1 Pflicht.
- Pro Spiel/Tag maximal NETRATTLER_MAX_BUILDERS_PER_MATCH_DAY (6). Integer-Linie = "N oder mehr".
- Modell-Builder (`netrattler_model_builders.py`, `netrattler_foul_props.py`): Fouls/Tackles ohne Buchmacherquote, faire Quote 1/p, Style "MODEL BUILDER", nie in die ROI-Zahl.
- Tackles-Historie: nur Premier League (FPL) + täglich wachsend über API-Football (100 Abfragen/Tag). ESPN liefert keine Tackles.

## Quellen und Grenzen (Stand 2026-10-28)
- The Odds API (Gratis, 500 Credits/Monat), API-Football (Gratis 100/Tag), SportsGameOdds (Gratis: nur MLS + CL, `netrattler_sgo_props.py`), ESPN, Football-Data, Pinnacle-Gastzugang, Betfair, OddsPapi.
- Geprüft, ohne Nutzen für Tackles/Fouls-Quoten: ParlayAPI (nur Tore), StrikerAPI (Torschützen), odds-api.io (Gratis-Keys pausiert, ab 49 £), Data'Scout (keine API).
- Top-5-Ligen: keine freie Quelle für Tackles-/Fouls-Quoten.

## Auswertungsstand (30 Tage)
- Over 2.5 ca. +14 % ROI (n=530), Corners hohe Trefferquote (Quoten prüfen, Verdacht auf unrealistische Quote), 1x2 negativ, Combo-Multi 3-11 Beine ca. 3-9 % Trefferquote -> auf max. 4 Beine begrenzt.
- Builder mit echter Quote: ROI deutlich negativ (n klein). Quote-lose Builder nie als ROI zählen.

## Kalibrierung (45 Tage, 2026-10-28)
- Brier-Score Modell vs. Markt (1/Quote): Modell ist in over25, btts, over15_ht, 1x2, btts_ht, combo schlechter als der Markt und teils schlechter als eine Münze; Modell ist 10-33 Prozentpunkte zu optimistisch (z.B. 1x2: Modell 62 %, real 37 %).
- Bestes Mischgewicht Modell vs. Markt: 0-10 % Modell bei 1x2, btts, btts_ht, combo. Vorsicht: Selektionsverzerrung (Tipps wurden dort gewählt, wo das Modell über dem Markt lag).
- Folge: "Edge" = Modell-p minus Marktwahrscheinlichkeit misst überwiegend Modellfehler. Schwellen nicht senken; Modell braucht echte Zusatzinformation (Aufstellungen, xG, Schiedsrichter) oder Wahrscheinlichkeiten werden zum Markt hin geschrumpft.
