# NETRATTLER – verbindliche Kartenreferenz (18.11.2026)

Zwei vom Betreiber bereitgestellte originale Screenshots sind ab 18.11.2026 die **Design-Master**:
1. **PROP BUILDER**: Liverpool vs Arsenal, 6 Spieler-Legs, Gold/Cyan-Stadion, L10/L15 rechts.
2. **GOAL HUNTER**: Hamburger SV vs Borussia Mönchengladbach, Terem Moffi, grossformatiges Spielerporträt.

Die Originalbilder dienen als visuelle Gestaltungsreferenzen, **nicht** als statisch mit falschen Spielern, Wappen oder Quoten bedruckter Kartenhintergrund. Alle variablen Inhalte müssen aus verifizierten echten Daten stammen.

## Einzufrierende Designmerkmale
- Nachtschwarzes Stadion **mit fotorealistischer Tribüne, Lichtmasten und echtem Rasen** statt einer flachen Farbfläche.
- Silber/weiss schräg gesetztes NETRATTLER-Logo; kleine goldene Krone darüber.
- Gelb-goldenes, stark leuchtendes schräges PROP BUILDER/GOAL HUNTER-Titelband mit Symbol.
- Weiche **Neon-Glows** an goldenen linken und cyanfarbenen rechten Kanten; sichtbare Tiefenwirkung und Lichtsäume.
- Korrekte echte Fussballwappen auf Team- und Spielerzeilen, keine Initialen oder Dummy-FC-Kreise.
- Echte Spielerporträts/Cutouts, gross links (Builder) bzw. zentral (Goal Hunter), nicht stilisierte Avatar-Silhouetten.
- Builder: klares 2–6-Leg-Raster; je Spieler Foto, Logo, Spielername, Markt, Balkensymbol sowie L10/L15. Langes Namensfeld nicht überschreiben.
- Goal Hunter: Spielerporträt und beide Teams mit grossen Logos; vier Kartenfelder für bestätigte Quote, Modellwahrscheinlichkeit, faire Quote und Tore pro Spiel.
- Fetter, kontrastreicher Auswertungsbalken unten; Telegram-Kennung am rechten Rand.
- **Keine Angaben als „—“ oder „Zeit nicht bestätigt“ in veröffentlichten Karten**. Unvollständige Karten bleiben intern und werden nicht versandt.

## Technische Freigabe
1. Datencheck vor Rendering: eindeutig zugeordnetes Team, überprüftes Foto, echte Wappen, bestätigte Kickoff-Zeit, gemessene L10/L15-Form.
2. Wirklich bestätigte **Kombiquote** für Builder; nie selbst multiplizierte Einzelquoten als buchbaren Kurs oder EV ausgeben.
3. Kontrolle **des finalen PNGs** mit `netrattler_visual_review.review_png`; fehlende Pixelbereiche, Texte, Fotos, Statistiken und abgeschnittene Footer blockieren Telegram.
4. GitHub-Actions-Workflow `netrattler_visual_cards_probe.yml` rendert Testkarten mit 2, 4, 6 Legs und Goal Hunter. Artifacts enthalten vier PNGs + `review.json`, und dienen der manuellen Gegenprüfung gegen die beiden Originalbilder.
5. Ein grüner Code-/Pixeltest **allein** beweist noch keine 1:1-Übereinstimmung. Der optische Abgleich der Testvorschauen bleibt zwingend und kann weitere Layout-Arbeit auslösen.
6. Tests nutzen bewusst synthetische Platzhalter statt realer Personen/Quoten; diese Testkarten dürfen **nicht** auf Telegram veröffentlicht werden.

## Noch sichtbare Abweichungen aus der QA-Runde am 18.11.
- Stadionhintergrund noch weniger fotorealistisch als die Originalvorlage (PIL-gezeichnete Tribüne statt Foto).
- Spieler im Test-Renderer noch in runden Fotos statt der freien Porträt-Cutouts aus der Vorlage.
- Typografie, Teamwappen-Beleuchtung und Leuchtspuren sind angenähert, aber noch nicht pixelgenau identisch.
- Mock-Testbilder bestätigen Geometrie, **nicht** Identität echter Spieler oder Live-Buchbarkeit einer Quote.

**Scope:** Nur PROP BUILDER und GOAL HUNTER erhalten diese Design-Umstellung. Alle übrigen NETRATTLER-Karten bleiben unverändert.
