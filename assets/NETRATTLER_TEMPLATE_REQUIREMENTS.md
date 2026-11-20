# NETRATTLER Telegram card templates — approved requirements (2026-11-19)

## Original sources — do not overwrite
- `assets/original_templates/NETRATTLER_BTTS_originalkarte.png`
- `assets/original_templates/NETRATTLER_BUILDER_4_originalkarte.png`
- `assets/original_templates/NETRATTLER_COMBO_7_originalkarte.png`
- `assets/original_templates/NETRATTLER_COMBO_9_originalkarte.png`
- `assets/original_templates/NETRATTLER_GOAL_HUNTER_originalkarte.png`
- `assets/netrattler_template_corner_original.webp`

These are unmodified user reference artworks, NOT cleaned render-ready masters. The sixteen `assets/premium_*_blank.svg` files are technical SVG skeletons, not sixteen user-original designs.

## COMBO card requirements
- Include a separate NETRATTLER COMBO card using the user's actual original artwork when supplied; do not fabricate or replace it with an approximate design.
- Show 3 to 10 combination legs with exactly that number of rows; remove unused rows and reposition the footer.
- Preserve blue/cyan and gold neon borders, display @prophunter, and render authentic, verified club crests for both teams in every leg (never generic shield placeholders). Include explicit 7-leg and 9-leg variants, as well as all other counts 3 through 10; number rows consecutively without duplicates.
- Both 7-leg and 9-leg COMBO source PNGs are present under `assets/original_templates/`. Their cleaned dynamic masters and Telegram production integration are **not yet complete**; do not mark them approved.

## Telegram handle (all NETRATTLER cards)
- Every NETRATTLER card, including PROP BUILDER, GOAL HUNTER, CORNER SNIPER and other groups, must display **@prophunter** (not @netrattler). The NETRATTLER brand/logo stays unchanged.
- Apply this to newly generated cards and the rendering code; updating these requirements alone does not change live Telegram cards.

## Visual rules
- Preserve the **actual uploaded/original** artwork, composition, crown, typography, dark stadium, **cyan/blue and gold/yellow neon outlines**. Do not recolor borders green. Green is permitted only for original statistical signals or values, not as replacement outlines.
- Clean out baked-in names, dates, numbers, odds, statistics, old player portraits and old team crests by restoring the underlying background. Do **not** conceal old text with opaque patches.
- Retain structural labels such as PROP BUILDER, GOAL HUNTER, CORNER SNIPER, labels for odds, probability, EV, confidence, settlement and @prophunter.
- At rendering time, add verified match names, team crests, licensed player portraits, lines, real bookmaker odds, L5/L10/L15 where relevant, model metrics, and original Telegram settlement status.
- PROP BUILDER must have exactly the actual number of player-leg rows (3, 4, 5 or 6), physically remove unused rows, reposition footer and crop card height. No blank rows.
- Use separate cleaned master assets and never overwrite the three originals.
- Visually compare output against the original templates, verify colors, leg count, text fitting, image placement, and test Telegram image update before production.

## Status
These are implementation requirements, **not finished cleaned image assets**. Mockup images generated in chat are not pixel-accurate edits and are **not** committed here.

## Unified premium design across all NETRATTLER groups
- Use the original blue/cyan + gold visual identity, NETRATTLER crown, authentic team crests and player photos where relevant, and @prophunter footer on every card.
- GOAL HUNTER: large real player portrait, both real club crests, goals/game, confirmed odds and probability.
- PROP BUILDER: 3–6 dynamic player rows, portraits, verified player markets, L5/L10/L15, no blank rows.
- CORNER SNIPER: authentic crests, corner L10/L15, verified H2H, tip and bookmaker odds.
- BTTS: both authentic crests, team-to-score stats and home/away form.
- OVER 1.5 / 2.5 and first-half markets: authentic crests, actual goal statistics, L10/L15, real odds.
- COMBO: 3–10 dynamic rows, premium larger row layout for 3–7, compact but readable for 8–10, no duplicated or empty rows.
- PLAYER PROPS: actual player portrait, market-specific stats (shots, fouls, tackles, cards), L5/L10/L15.
- LAST MINUTE GOAL: live score, verified match minute, pressure metrics and real current odds; avoid stale data.
- Other groups: same branding, but market-appropriate labels and verified statistics.
- Always include original-message settlement status (open/won/lost/void) and a visual QA gate checking crest/portrait presence, alignment, readability, row counts and accurate footer.
- Never invent or infer betting odds, outcomes or statistics for production cards. Visual demo examples are not live picks.
- These are approved design requirements only; implementation, testing and Telegram rollout remain separate tasks.

## Full category coverage checklist (design specification, not deployment verification)
- BTTS; Over 1.5 / Over 2.5 / Over 3.5; BTTS first half; Over 1.5 first half; 1X2 and Double Chance; Match Stats.
- Combo / Multi (3–10 legs); Goal Hunter / Goalscorer; Prop Builder (3–6 players); Player Props (shots, shots on target, assists, cards, corners, tackles, fouls); Fouls / Tackles / Cards; Corner Sniper; VAR.
- Last Minute Goal; Late Goals; Live Half-Time; Cross / Mix and mixed-market Builder.
- Reuse market-specific visual components, but keep consistent NETRATTLER logo, blue/cyan-gold frame, authentic assets, verified odds, settlement, and @prophunter.
- Coverage in this checklist means **design requirements only**, not evidence that every Telegram group is currently sending premium cards.
