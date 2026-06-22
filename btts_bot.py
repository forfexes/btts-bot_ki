-- Nur falls ml_tips noch nicht existiert:
CREATE TABLE IF NOT EXISTS ml_tips (
    id              bigserial PRIMARY KEY,
    match_id        text NOT NULL,
    home_team       text,
    away_team       text,
    league          text,
    date            text,
    time            text,
    market          text,
    tip             text,
    odds            float,
    confidence      int,
    probability     float,
    value_rating    text,
    features        jsonb,
    created_at      timestamptz DEFAULT now(),
    bot_version     text DEFAULT '3.0',
    result          text,
    settled         boolean DEFAULT false,
    settled_at      timestamptz,
    actual_score    text
);

CREATE INDEX IF NOT EXISTS ml_tips_match_id_idx ON ml_tips (match_id);
CREATE INDEX IF NOT EXISTS ml_tips_settled_idx  ON ml_tips (settled, created_at);
CREATE INDEX IF NOT EXISTS ml_tips_market_idx   ON ml_tips (market);

ALTER TABLE ml_tips ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ml_tips_read" ON ml_tips;
CREATE POLICY "ml_tips_read" ON ml_tips FOR SELECT USING (true);
