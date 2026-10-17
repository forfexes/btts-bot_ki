# Supabase pg_cron jobs (Stand 2026-10-17)

Diese Jobs laufen direkt in der Datenbank (nicht in GitHub Actions).
Abfrage: `select jobname, schedule, command from cron.job;`

| Job | Zeit (UTC) | Wirkung |
| --- | --- | --- |
| `l20-prune-player-stats` | 03:00 täglich | `player_match_stats`: nur die letzten 20 Spiele pro Spieler/Team |
| `trim-odds-history-7d` | 03:05 täglich | `odds_history`: Live-Quoten älter als 7 Tage löschen (siehe unten) |
| `prune_player_prop_db` | 03:15 täglich | `player_prop_db` älter als 3 Tage löschen |
| `prune_source_health` | 03:25 täglich | `source_health` älter als 14 Tage löschen |
| `weekly-analyze` | 04:00 sonntags | `ANALYZE` auf `player_match_stats`, `odds_history` |

## Änderung 2026-10-17: `trim-odds-history-7d`

Vorher: `DELETE FROM odds_history WHERE captured_date < CURRENT_DATE - 7 days`
(ohne Quellen-Filter).

Problem: Alle 104.713 historischen Trainings-Quoten (`football_data_co_uk`,
Saisons ab 2023) tragen das `captured_date` ihres letzten Imports
(2026-10-11). Sie werden nur sonntags 03:35 UTC vom Odds-Harvester neu
importiert. Fällt dieser eine Import aus, hätte der Job am nächsten Tag die
komplette historische Quoten-Basis der Modelle gelöscht.

Jetzt: Live-Quoten wie bisher 7 Tage. Eine `football_data_co_uk`-Kopie wird
erst gelöscht, wenn eine neuere Kopie existiert. Probelauf für 2026-10-19 bei
fehlgeschlagenem Import: 0 historische Zeilen gelöscht, 85.931 Live-Zeilen
wie vorgesehen entfernt.
