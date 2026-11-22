# NETRATTLER AI – Premium Fouls Builder (22.11.2026)

## Was implementiert ist

- netrattler_foul_props.py: 15 echte letzte Spiele, getrennte Fouls begangen/erlitten und Einsatzminuten.
- netrattler_fouls_builder_premium.py: strenger Same-Match-Prüfer, API-Football-Startelfadapter und interne Kandidatensuche für 2+/3+ Fouls.
- netrattler_lineup_builders.py: echte Team-IDs und 11+11 bestätigte Starter in getrennten Listen; reine Analyse, ohne automatischen Telegram-Post.
- netrattler_model_builders.py und netrattler_builder_cards.py: alte unbepreiste Nate-/Fouls-Builder sind vor DB-Reservierung beziehungsweise vor Telegram gesperrt.

Die historischen Screenshots mit 7/1 und 60/1 sind Beispiele, keine aktuellen Angebote oder Belege für einen langfristigen Wettvorteil.

## Regeln für Spieler und Statistiken

Ein Tipp benötigt exakte Fixture-ID, richtige Heim- und Gast-Team-IDs, Status NS, kommenden Anpfiff, vollständige bestätigte Startelf und eine eindeutige Spielerzuordnung zum richtigen Klub. Keine übergreifende Fuzzy-Zuordnung. Die L5-/L10-/L15-Angaben sind **historische Trefferzahlen**, keine automatisch kalibrierten Gewinnwahrscheinlichkeiten. p90 gibt es nur mit beobachteten Minuten. Fehlende Daten bleiben fehlend; keine Nullauffüllung.

Spieler fremder Vereine, selbst wenn sie zusammen mit anderen Spielern auf einem Screenshot gezeigt werden, dürfen nicht unbemerkt im selben Spiel-Builder erscheinen.

## Buchmacherquote – keine Modell- oder Screenshotquote

Ein publizierbarer Builder braucht eine echte **kombinierte** Buchmacher-Offerte mit Bookmaker-Namen, Ticket-ID, unveränderten Fixture- und Team-IDs, gültigem Zeitstempel (max. 20 Minuten alt), realen Selection-IDs und 3–6 einmaligen Spieler-Legs. Beide Märkte, Fouls begangen und Fouls erlitten, müssen vertreten sein. Standard: **1 Unit**.

Die kombinierten Decimal Odds werden nie durch Multiplikation von Einzelquoten als Buchmacherquote ersetzt. Die Rechnung 100 / kombinierte Quote ergibt lediglich die **implizierte Wahrscheinlichkeit**. Eine verifizierte gemeinsame Modellwahrscheinlichkeit, EV und ROI werden ohne gesonderte Kalibrierung nicht behauptet.

Der Prüfer validiert die Konsistenz einer übergebenen Offerte. Er greift selbst nicht beim Buchmacher zu und kann einen erfundenen Eingabedatensatz nicht unabhängig authentifizieren.

## Produktiv-Freigabe bleibt gesperrt

Die neue Kandidatensuche läuft nur als Forschungslog. Der produktive Aufstellungs-Workflow ist pausiert. Es fehlen weiterhin:

1. Ein funktionierender angebundener Provider für **tatsächlich angebotene kombinierte Same-Game-Fouls-Tickets**.
2. Ein sauberer, vom Nutzer visuell freigegebener **Original-Fouls-Builder-Master**, der keine alten Werte übermalt.
3. Bestätigte echte Telegram-Bildansicht, Wappen/Spielerfotos, Auswertung in derselben Nachricht und Send-/Edit-Receipt.

Kein Ersatzdesign und kein Text-Fallback. Ein grüner Offline-Test ist **keine** Freigabe für Telegram.

## Aktueller Test

NETRATTLER Fouls Builder Premium Hardtest:
https://github.com/forfexes/btts-bot_ki/actions/runs/45021422613

Er prüft die Spieleridentität, 22 Starter, echte Ticketevidenz, L10/L15, historische Statistik, interne Live-Scouting-Anbindung und Sperren der alten Bild-/Versandwege.
