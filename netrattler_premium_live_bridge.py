"""Strict verified-data bridge to NETRATTLER AI PREMIUM mobile cards.

Consumes existing bookmaker-observed tip dictionaries and identity-matched,
transparent provider PNG/WebP bytes. No fetching, Telegram calls, screenshots,
style changes, synthetic odds or persistent image cache. Fail closed.
"""
from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from PIL import Image

from netrattler_premium_mobile_pages import render_mobile_pages, MASTER_PATH
from premium_joint_formula import estimate_combo
from netrattler_premium_mobile_telegram_plan import plan_new_ticket

ALIASES = {
    "btts": ("btts", "BTTS · BEIDE TEAMS TREFFEN"),
    "over25": ("over", "OVER 2.5 TORE"),
    "btts_ht": ("btts_halftime", "BTTS · 1. HALBZEIT"),
    "over15_ht": ("over_halftime", "OVER 1.5 · 1. HALBZEIT"),
    "1x2": ("match_result", "1X2"),
    "corners": ("corner", "ECKBAELLE"),
    "cards": ("fouls_cards", "KARTEN / FOULS"),
    "props": ("player_props", "SPIELER-PROP"),
    "advanced_props": ("player_props", "SPIELER-PROP"),
    "scorer": ("goal", "TORESCHUETZE"),
    "var": ("var", "VAR-EREIGNIS"),
}
MULTI_TYPES = {"builder", "combo", "cross_mix", "lottery"}
PRICE_FIELDS = ("bookmaker_odds", "oddsYes", "odds", "odd", "price")


def _split_match(text):
    text = str(text or "").strip()
    match = re.split(r"\s+(?:vs\.?|v\.?|-)\s+", text, maxsplit=1, flags=re.I)
    if len(match) != 2 or not all(t.strip() for t in match):
        raise ValueError("Two unambiguous clubs required in the source fixture")
    home, away = (t.strip() for t in match)
    if home.casefold() == away.casefold():
        raise ValueError("Home and away clubs must differ")
    return home, away


def _book_price(record):
    if not isinstance(record, dict):
        raise ValueError("Leg data must be a dictionary")
    for label in ("_no_real_odds", "_synthetic", "synthetic", "estimated_odds",
                  "estimated", "odds_calculated", "model_odds"):
        if record.get(label):
            raise ValueError("Unverified or estimated individual quote is not permitted")
    # Generic feed fields (_source/source) often contain ESPN, API-Football
    # or another statistical provider. They are NEVER bookmaker evidence.
    # Accept only explicitly marked sportsbook provenance on real leg prices.
    kind = str(record.get("price_type") or "").lower().strip()
    if (record.get("odds_observed") is False
            or kind in {"synthetic", "estimated", "model", "model_odds",
                        "calculated_from_leg_odds", "derived_builder"}
            or record.get("price_calculated") is True):
        raise ValueError("Unverified synthetic/model leg quote cannot be published")
    source = str(record.get("bookmaker") or record.get("book")
                 or record.get("bookie") or record.get("odds_source") or "").strip()
    if not source or source.casefold() in {"model", "espn", "fotmob", "apifootball",
                "api-football", "statsbomb", "forebet", "synthetic", "estimated"}:
        raise ValueError("Named sportsbook/bookmaker provenance required for every selection")
    for field in PRICE_FIELDS:
        raw = record.get(field)
        try:
            price = float(raw)
        except (ValueError, TypeError, OverflowError):
            continue
        if math.isfinite(price) and 1.0 < price < 100000:
            return price, source
    raise ValueError("Observed bookmaker selection quote unavailable")


def _raw_asset(payload, label, minimum=40):
    if not isinstance(payload, (bytes, bytearray)) or not 200 < len(payload) < 8_000_000:
        raise ValueError("Missing authentic image bytes: " + label)
    try:
        with Image.open(BytesIO(payload)) as opened:
            opened.load()
            if opened.format not in ("PNG", "WEBP"):
                raise ValueError("Provider asset must have real transparency")
            im = opened.convert("RGBA")
    except (OSError, SyntaxError) as exc:
        raise ValueError("Undecodable authentic image: " + label) from exc
    if min(im.size) < minimum or im.getchannel("A").getextrema()[0] >= 255:
        raise ValueError("Provider supplied opaque or tiny asset: " + label)
    alpha = im.getchannel("A")
    bbox = alpha.point(lambda a: 255 if a >= 24 else 0).getbbox()
    if not bbox:
        raise ValueError("Empty transparent provider asset: " + label)
    corners = ((0, 0), (im.width-1, 0), (0, im.height-1), (im.width-1, im.height-1))
    if all(alpha.getpixel(corner) >= 24 for corner in corners):
        raise ValueError("Opaque rectangular sticker masquerading as cutout: " + label)
    return im


def _market_category(record, forced=None):
    market = str(record.get("market") or "").strip().lower()
    # VAR observations are not enough: the same verified rule coverage
    # is mandatory inside a builder as on a single VAR card.
    if market == "var" and (record.get("tip_eligible") is not True
                            or record.get("settlement_rule_verified") is not True):
        raise ValueError("VAR settlement rules are not verified")
    if forced and forced in MULTI_TYPES:
        category = forced
        display = str(record.get("market_label") or record.get("market_display") or "").strip()
        # A bare selection such as YES / NO is NOT a market. Recover a label
        # only from a known market identifier, preserving the actual direction.
        if not display and market in ALIASES:
            _, display = ALIASES[market]
            direction = str(record.get("selection") or record.get("tip") or "").strip().upper()
            if market == "1x2":
                if direction not in {"1", "X", "2", "1X", "X2", "12"}:
                    raise ValueError("Invalid builder 1X2 selection")
                display += " · " + direction
            elif direction in {"YES", "JA"}:
                display += " · JA"
            elif direction in {"NO", "NEIN"}:
                display += " · NEIN"
        if not display:
            raise ValueError("Each builder/combo selection needs an actual market label")
        return category, display
    if market in ALIASES:
        category, display = ALIASES[market]
        direction = str(record.get("selection") or record.get("tip") or "").strip().upper()
        if market in {"btts", "over25", "btts_ht", "over15_ht", "var"}:
            if direction in {"NO", "NEIN", "FALSE", "0", "UNDER", "UNTER"}:
                raise ValueError("Verified YES card must not reverse an explicit NO selection")
        if market == "var":
            if record.get("tip_eligible") is not True or record.get("settlement_rule_verified") is not True:
                raise ValueError("VAR settlement rules are not verified")
            from datetime import datetime
            kickoff = str(record.get("commence_time") or "")
            try:
                value = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError("Naive kickoff")
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("VAR requires verified timezone-aware kickoff") from exc
        if market == "1x2":
            if direction not in {"1", "X", "2", "1X", "X2", "12", "HOME", "DRAW", "AWAY"}:
                raise ValueError("1X2 selection missing or invalid")
            display += " · " + direction
        elif direction in {"YES", "JA"} and market in {"btts", "btts_ht", "var"}:
            display += " · JA"
        return category, str(record.get("market_display") or display).strip()
    category = str(forced or record.get("category") or "").lower()
    if category not in MULTI_TYPES:
        raise ValueError("Unsupported observed market, no silent generic fallback")
    display = str(record.get("market_label") or record.get("market_display") or "").strip()
    if not display:
        raise ValueError("A verified market label is required")
    return category, display


def _ticket_quote(record, multi):
    """Return observed ticket quote or explicit product of genuine leg odds.

    Never carry an estimated existing total forward as a bookmaker offer.
    Unverified/correlated builder products are analysis values, not betslips.
    """
    if not multi:
        return {}
    features = record.get("features") if isinstance(record.get("features"), dict) else {}
    observed = (record.get("combined_odds_observed") is True
                or features.get("combined_odds_observed") is True)
    receipt = str(record.get("combined_quote_id")
                  or features.get("combined_quote_id") or "").strip()
    tainted = any(
        scope.get("combined_quote_calculated") is True
        or scope.get("combined_odds_calculated") is True
        or scope.get("builder_odds_estimated_from_legs") is True
        or str(scope.get("price_type") or "").lower() in
        {"estimated", "derived_builder", "calculated_from_leg_odds"}
        for scope in (record, features)
    )
    if observed:
        if tainted or not receipt:
            raise ValueError("Contradictory or unverified observed bookmaker ticket receipt")
        raw = record.get("combined_odds")
        if raw is None:
            raw = record.get("total_odds")
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Observed bookmaker ticket quote unavailable") from None
        if not math.isfinite(value) or not 1 < value < 100000:
            raise ValueError("Invalid observed bookmaker combined quote")
        return {"combined_odds": value, "combined_odds_observed": True,
                "combined_ticket_id": receipt}
    # No confirmed full-ticket receipt: recompute exclusively from independently
    # verified single-leg bookmaker odds, never record.total_odds.
    verified = []
    for leg in record.get("legs") or []:
        price, _ = _book_price(leg)
        verified.append({"odds": price, "odds_observed": True,
                         "match": leg.get("match"), "event_id": leg.get("event_id")})
    estimate = estimate_combo(verified)
    product = estimate["indicative_leg_product"]
    if product is None or not estimate["individual_prices_observed"]:
        raise ValueError("Formula requires independently observed leg quotes")
    return {"combined_odds": product, "combined_odds_observed": False,
            "combined_odds_calculated": True,
            "price_type": "calculated_from_leg_odds",
            "combined_scope": estimate["scope"]}


@contextmanager
def prepare_verified_ticket(record, *, crest_provider, player_provider=None):
    """Yield (data, master) while temporary genuine source assets exist.

    Provider contracts are crest_provider(exact_team)->bytes and
    player_provider(exact_full_name, confirmed_club)->bytes.
    Caller MUST verify athlete/team identities before supplying their images.
    """
    if not isinstance(record, dict):
        raise ValueError("A source ticket dictionary is required")
    category = str(record.get("category") or "").lower()
    multi = category in MULTI_TYPES
    records = record.get("legs") if multi else [record]
    if not isinstance(records, list) or not 1 <= len(records) <= 10:
        raise ValueError("1..10 actual source selections required")
    if multi and len(records) < 2:
        raise ValueError("Combined ticket requires at least two selections")
    if not callable(crest_provider):
        raise ValueError("Authentic club crest provider required")
    id_ = str(record.get("ticket_id") or "").strip()
    if not id_:
        raise ValueError("Stable source ticket_id required for settlement")
    if float(record.get("stake_units", 1.0)) != 1.0:
        raise ValueError("One 1u ticket is required")
    status = str(record.get("status") or "OFFEN").strip().upper()
    if status not in {"OFFEN", "GEWONNEN", "VERLOREN", "PUSH", "VOID"}:
        raise ValueError("Unknown source settlement result")
    data = {"category": category, "legs": [], "ticket_id": id_,
            "stake_units": 1, "status": status}
    data.update(_ticket_quote(record, multi))
    prob = record.get("model_probability")
    if prob is not None:
        p = float(prob)
        if not math.isfinite(p) or not 0 <= p <= 100:
            raise ValueError("Invalid explicit model probability")
        data["model_probability"] = p
    with TemporaryDirectory(prefix="netrattler_real_assets_") as temp:
        cache = {}
        def picture(payload, key, minimum):
            if key not in cache:
                im = _raw_asset(payload, key, minimum)
                path = Path(temp) / (str(len(cache)+1) + ".png")
                im.save(path)
                cache[key] = str(path)
            return cache[key]
        for n, leg in enumerate(records, 1):
            kind, market = _market_category(leg, category if multi else None)
            if not multi:
                data["category"] = kind
            price, bookmaker = _book_price(leg)
            home, away = _split_match(leg.get("match"))
            homepath = picture(crest_provider(home), "club:"+home.casefold(), 40)
            awaypath = picture(crest_provider(away), "club:"+away.casefold(), 40)
            picked = {"match": str(leg["match"]).strip(), "market": market,
                      "bookmaker_odds": price, "bookmaker": bookmaker,
                      "home_logo": homepath, "away_logo": awaypath}
            player = str(leg.get("player") or "").strip()
            if player:
                club = str(leg.get("team") or "").strip()
                if club.casefold() not in {home.casefold(), away.casefold()}:
                    raise ValueError("Player's verified club must equal one of this fixture's teams")
                if not callable(player_provider):
                    raise ValueError("Genuine identity-matched player cutout provider required")
                picked["player"] = player
                picked["player_photo"] = picture(player_provider(player, club),
                                                  "player:"+player.casefold()+"@"+club.casefold(), 80)
            for optional in ("form", "result"):
                if leg.get(optional):
                    picked[optional] = str(leg[optional])
            data["legs"].append(picked)
        yield data, MASTER_PATH


def verified_mobile_images(record, *, crest_provider, player_provider=None):
    with prepare_verified_ticket(record, crest_provider=crest_provider,
                                 player_provider=player_provider) as (data, master):
        pages = render_mobile_pages(master, data, preview_only=False)
        return [page.image.copy() for page in pages]


def verified_telegram_payload_plan(record, chat_id, *, crest_provider,
                                   player_provider=None):
    """Prepare, never send, real-image album payloads for final owner QA."""
    with prepare_verified_ticket(record, crest_provider=crest_provider,
                                 player_provider=player_provider) as (data, master):
        return plan_new_ticket(data, chat_id, master=master, preview_only=False)


def builder_preview_record(pick):
    """Convert normalized BuilderPick into the original-card QA contract.

    No Telegram transport, receipt synthesis, or master approval occurs here.
    Recompute the formula from observed legs; ignore the cached total_odds.
    """
    from datetime import datetime, timezone
    from netrattler_builder_engine import is_bookmaker_source
    from netrattler_builder_cards import builder_leg_label
    legs = list(getattr(pick, "legs", []) or [])
    if not 2 <= len(legs) <= 7:
        raise ValueError("Builder requires 2-7 verified legs")
    ticket_id = str(getattr(pick, "builder_id", "") or "").strip()
    if not ticket_id:
        raise ValueError("Missing builder identity")
    result = []
    for leg in legs:
        source = str(getattr(leg, "source", "") or "").strip()
        if (not is_bookmaker_source(source) or getattr(leg, "estimated", False)
                or ":derived" in source.lower()):
            raise ValueError("Unverified individual builder price")
        kickoff = datetime.fromisoformat(str(getattr(leg, "kickoff", "")).replace("Z", "+00:00"))
        if kickoff.tzinfo is None or kickoff.utcoffset() is None or kickoff <= datetime.now(timezone.utc):
            raise ValueError("Builder requires verified future kickoff")
        home, away = _split_match(getattr(leg, "match", ""))
        player = str(getattr(leg, "player", "") or "").strip()
        team = str(getattr(leg, "team", "") or "").strip()
        if not player or team.casefold() not in {home.casefold(), away.casefold()}:
            raise ValueError("Builder requires identity-matched athlete and club")
        label = builder_leg_label(leg)
        if not label or "Linie prüfen" in label:
            raise ValueError("Builder requires verified market and threshold")
        record = {"match": leg.match, "market_label": label, "player": player,
                  "team": team, "bookmaker_odds": leg.odds, "bookmaker": source,
                  "odds_observed": True, "commence_time": kickoff.isoformat()}
        _book_price(record)
        result.append(record)
    category = "cross_mix" if len({r["match"].casefold() for r in result}) > 1 else "builder"
    return {"ticket_id": ticket_id, "category": category, "legs": result,
            "stake_units": 1, "combined_odds_observed": False, "status": "OFFEN"}


def builder_offline_payload_plan(pick, chat_id, *, crest_provider, player_provider):
    """Plan original-style Builder images only; never dispatch or approve."""
    return verified_telegram_payload_plan(builder_preview_record(pick), chat_id,
        crest_provider=crest_provider, player_provider=player_provider)
