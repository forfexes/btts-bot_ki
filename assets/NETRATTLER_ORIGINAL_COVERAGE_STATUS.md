# NETRATTLER – Originalbild-Abdeckung (GitHub-Audit 21.11.2026)

Status: **NICHT für alle Wettarten liegen eigenständige vom Nutzer gelieferte Originalbilder vor.**

## Verifizierte unveränderte Referenzdateien

| Familie | Pfad | Status |
|---|---|---|
| BTTS | `assets/original_templates/NETRATTLER_BTTS_originalkarte.png` | Original-Referenz vorhanden |
| Prop Builder 4 | `assets/original_templates/NETRATTLER_BUILDER_4_originalkarte.png` | Original-Referenz vorhanden |
| Combo 7 | `assets/original_templates/NETRATTLER_COMBO_7_originalkarte.png` | Original-Referenz vorhanden |
| Combo 9 | `assets/original_templates/NETRATTLER_COMBO_9_originalkarte.png` | Original-Referenz vorhanden |
| Goal Hunter | `assets/original_templates/NETRATTLER_GOAL_HUNTER_originalkarte.png` | Original-Referenz vorhanden |
| Prop Builder (WebP) | `assets/original_templates/prop_builder_original.webp` | Original-Referenz vorhanden; dynamische 2–6-Leg-Version im Code |
| Goal Hunter (WebP) | `assets/original_templates/goal_hunter_original.webp` | Original-Referenz vorhanden; dynamische Karte im Code |
| Corner Sniper (WebP) | `assets/netrattler_template_corner_original.webp` | Original-Referenz vorhanden |

=> **8 Referenzdateien für 6 Kartentyp-Familien** (zwei davon mit zusätzlichen Referenzen).

Die Dateien `assets/netrattler_template_builder_original.webp` und
`assets/netrattler_template_goal_original.webp`, obwohl in einem älteren Workflow
als Pfade erwähnt, existieren nicht. Nicht als Original zählen.

## Vollständiger Soll-Katalog der 16 technischen Kartenfamilien

| Kartentyp | Eigenständiges Original? | Ist-Zustand |
|---|---|---|
| builder | JA, 4-Leg PNG + WebP | Echter Original-Renderer vorhanden; dynamische Varianten nicht automatisch eigene Originale |
| goal | JA, PNG + WebP | Echter Original-Renderer vorhanden |
| corner | JA, WebP | Corner-Sniper-Renderer vorhanden |
| btts | JA, PNG | Original-Renderer vorhanden |
| combo | TEILWEISE, 7/9 PNG | 3–6, 8, 10 haben keine jeweils eigene Originalvorlage |
| over | NEIN | Technisches SVG, kein Original |
| btts_halftime | NEIN | Technisches SVG, kein Original |
| over_halftime | NEIN | Technisches SVG, kein Original |
| match_result | NEIN | Technisches SVG, kein Original |
| player_props | NEIN | Technisches SVG, kein Original |
| fouls_cards | NEIN | Technisches SVG, kein Original |
| var | NEIN | Technisches SVG, kein Original |
| last_minute_goal | NEIN | Technisches SVG, kein Original |
| late_goals | NEIN | Technisches SVG, kein Original |
| live_halftime | NEIN | Technisches SVG, kein Original |
| cross_mix | NEIN | Technisches SVG, kein Original |

Abgeleitete Ziele wie Over 1.5/2.5/3.5, 1X2/Double Chance,
Shots/SOT, Fouls/Tackles/Karten, Live-Halbzeit, Late-Goal und Match Stats
sind damit noch **nicht alle durch eigenständige Originalgrafiken belegt**.

**WICHTIG:** Die 16 `assets/premium_*_blank.svg` sind technische SVG-Skeletons,
KEINE 16 vom Nutzer zur Verfügung gestellten Originalgrafiken.
Die Existenz eines Referenzbilds beweist auch keinen erfolgreichen Telegram-Produktivversand.

## Dynamische Ableitung aus echten Originalen (21.11.2026)

- **PROP BUILDER 2–7 Legs:** Renderpfad verwendet die echte
  `assets/original_templates/prop_builder_original.webp` als unveränderte
  Quelle, entfernt unbenutzte Zeilen und repositioniert den Footer.
- **COMBO 3–12 Legs:** Der Produktions-nahe Kartenrenderer
  `netrattler_combo_dynamic_cards.render_combo` verwendet ausschliesslich
  `NETRATTLER_COMBO_7_originalkarte.png` für 3–7 Legs und
  `NETRATTLER_COMBO_9_originalkarte.png` für 8–12 Legs. Die Varianten
  erhalten echte Original-Kopf-/Fussbereiche; 7/9-Quellen bleiben unverändert.
  Es werden **keine** generischen Ersatzkarten erzeugt.
- Die Ableitungen sind **keine neuen vom Nutzer hochgeladenen Originaldateien**.
  Sie werden aus den Originaldateien bei Bedarf als PNG gerendert.
- Für 3/4/5/6/8/10/11/12 Combo sowie 2/3/4/5/6/7 Builder existieren
  Offline-Regressionstests. Ein GitHub-Workflow exportiert synthetische QA-PNGs.
- **Noch nicht bestätigt:** Grüner CI-Lauf, visuelle Freigabe aller Varianten,
  durchgängig verdrahteter produktiver Telegram-Versand; der Renderer allein
  belegt keine erfolgreiche Telegram-Veröffentlichung.

## Verbindliche Handhabung

1. Echte Originaldateien unverändert aufbewahren und niemals durch generische Entwürfe ersetzen.
2. Weitere Originaldateien nur dann als `Original` kennzeichnen, wenn eine tatsächlich vom Nutzer gelieferte Referenz vorhanden und ihre Identität überprüft ist.
3. Für fehlende Kategorien ausdrücklich `Original noch nicht vorhanden` melden – niemals eine aus einem SVG erzeugte Karte als Original ausgeben.
4. Berechnete Combo-/Builder-Quoten als **berechnet / unbestätigt** markieren; ohne bestätigte Buchmacherquote keinen kombinationsbezogenen EV oder realisierten ROI ausweisen.
5. Bild-QA, Offline-Tests und produktiven Telegram-Versand separat verifizieren; keine Erfolgsbehauptungen nur aufgrund der Dateipräsenz.
