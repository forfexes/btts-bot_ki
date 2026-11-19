# NETRATTLER Premium-Karten: Status (19.11.2026)

Die bestehenden Premium-Masters (`assets/premium_*_blank.svg`) und die Premium-Renderer für Match-Karten,
Builder und Goal Hunter sind **unverändert**. Neu sind nur die fehlenden Premium-Wege.

## Kategorien und Renderer (alle 16 auf Premium-Masters)
| Kategorie | Renderer | Produktiver Versandweg |
|---|---|---|
| btts, over, btts_halftime, over_halftime, match_result, cross_mix (BTTS+Over) | `netrattler_premium_telegram_adapter` (unverändert) | `send_cards` → `render_card` |
| Mehrere Märkte eines Spiels / historische Gruppenkarten mit Ergebnis | `netrattler_premium_extra.render_combo(category="cross_mix")` (2–6 Zeilen) | `render_card` (BIS-Altdesign entfernt) |
| builder | `netrattler_original_template_renderer.render_builder` (2–6 Legs) | `send_builder_card` |
| goal | `render_goal` (unverändert) | `send_scorer_card` |
| corner | `netrattler_premium_extra.render_corner` | `send_corner_card`, `send_cards` |
| last_minute_goal | `netrattler_premium_extra.render_lmg` | `netrattler_lmg_free.send_alert` / `lmg_settle` |
| combo (3–10 Legs) | `netrattler_premium_extra.render_combo` | Zusatzbild nach dem Combo-Text in `btts_bot.py` (Text-Message-ID bleibt) |
| fouls_cards, var, late_goals, live_halftime, player_props | `netrattler_premium_extra.render_match_stats` | **noch kein produktiver Tipp-Strom** (siehe unten) |

## Änderungen
* Hardtest-Fehler: Builder-Test und Visual-Review verglichen mit der entfernten WebP-Vorlage; jetzt gegen kompakte SVG-Masters (2–6 Legs).
* `@netrattler` → `@prophunter` in `netrattler_neon_design.py`, `netrattler_corner_template.py`; Test verbietet `@netrattler` in allen `netrattler_*.py`.
* Corner und Last Minute Goal brauchten fehlende WebP-Originale (Karten wurden nie gesendet) → jetzt Premium-SVG.
* Combo 3–10 mit beiden Vereinswappen pro Zeile; Cross/Mix 2–6.
* L5/L10/L15: Builder zeigt jede Periode, für die echte Historie existiert (min. L5), sonst «—». Corner zeigt L10/L15 nur aus echten Tipp-Daten.
* Fail-closed: kein Wappen/Foto, keine echte Quote oder Quelle → keine Karte. Keine Platzhalter («WAPPEN FEHLT» entfernt).
* Nachrichten-IDs: Ergebnis-Updates ändern dieselbe Karte per editMessageMedia; das Combo-Zusatzbild wird nicht gespeichert, die Text-ID bleibt.
* Void wird auf Karten angezeigt (siehe frühere Änderung).

## Tests
* `test_netrattler_premium_all_cards.py` (43 Tests): PNG-Format, Grösse, Wappen/Zeilen/Panels pixelgeprüft gegen Master, Header unverändert, `@prophunter` vorhanden, Combo 3–10, Cross/Mix 2–6, Fail-closed, Netzwerk im Test gesperrt.
* Offline-Sandbox-Hardtest: alle Schritte lokal grün (kein Telegram-/Supabase-Zugriff, Tokens leer).
* Gesamtsuite vs. main: 19 → 6 Fehler, keine neuen.

## Verbleibende Fehler / offene Punkte
1. `test_train_honest_eval.py` (3 Tests, `AttributeError`) und 14 Fixture-Errors in `test_netrattler_regression_step1/stability_step2/step3` waren schon auf main kaputt, nicht Teil dieses PR. `test_netrattler_core.py` bricht schon beim Import ab (`Observed match markets were not normalized`).
2. Fouls/Karten, VAR, Late Goals, Live-Halbzeit und Player Props haben Renderer, aber im Repo keinen Tipp-Strom, der sie ruft. Sobald solche Tipps (`market` + echte Quote + Quelle) in `tips_by_market` liegen, fehlt nur das Mapping in `render_card`.
3. Premium-Masters sind technische Vorlagen, keine Original-Artworks; die Originale (`netrattler_template_*_original.webp`) liegen nicht im Repo.
4. L5/L10/L15 für Team-Märkte (BTTS/Over) fehlen: `attach_history_context` liefert keine Serien, nur Form und Durchschnitte.
5. Kein Live-Test in Telegram (bewusst); die Darstellung in Telegram ist nicht geprüft.
