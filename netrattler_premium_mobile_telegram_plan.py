"""Offline Telegram image-album and in-place settlement plans for premium cards.

This module NEVER makes HTTP requests. It supplies upload payloads only after
rendering safe-zone-padded images from the immutable original master.
Live transport requires an explicit, separate visual/Telegram release decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from typing import Any

from netrattler_premium_mobile_pages import render_mobile_pages, MASTER_PATH
from netrattler_telegram_safe_zone import append_safe_margin, assert_safe_margin


@dataclass(frozen=True)
class TelegramPlan:
    method: str
    data: dict[str, str]
    files: dict[str, tuple[str, bytes, str]]
    page_ranges: tuple[tuple[int, int], ...]


def plan_new_ticket(ticket: dict, chat_id: str, *, master=MASTER_PATH,
                    preview_only: bool=False) -> TelegramPlan:
    """Prepare one sendPhoto or one sendMediaGroup (2..10 pages); no network."""
    if not isinstance(chat_id,str) or not chat_id.strip():
        raise ValueError("Target Telegram chat must be explicitly supplied")
    pages = render_mobile_pages(master, ticket, preview_only=preview_only)
    if not 1 <= len(pages) <= 10:
        raise ValueError("Telegram media albums may contain only 2..10 media")
    attachments={}
    for page in pages:
        buf=BytesIO()
        page.image.save(buf,format="PNG",optimize=True)
        original=buf.getvalue()
        padded=append_safe_margin(original)
        assert_safe_margin(original,padded)
        name=f"card_{page.page}"
        attachments[name]=(f"netrattler_premium_{page.page:02d}.png",padded,"image/png")
    if len(pages)==1:
        method="sendPhoto"
        data={"chat_id":chat_id,"disable_notification":"true"}
        files={"photo":attachments["card_1"]}
    else:
        method="sendMediaGroup"
        items=[{"type":"photo","media":f"attach://card_{page.page}"}
               for page in pages]
        # Only the first album photo has a caption. No separate text messages.
        items[0]["caption"]=(f"NETRATTLER AI PREMIUM · EIN TICKET · "
                            f"{len(ticket['legs'])} TIPPS · 1 UNIT GESAMT")
        data={"chat_id":chat_id,"media":json.dumps(items,ensure_ascii=False),
              "disable_notification":"true"}
        files=attachments
    return TelegramPlan(method,data,files,tuple((p.first_leg,p.last_leg) for p in pages))


def bind_message_ids(plan: TelegramPlan, message_ids: list[int], ticket_id: str) -> dict:
    """Persist the exact original photo IDs; never infer a Telegram message ID."""
    if not isinstance(ticket_id,str) or not ticket_id.strip():
        raise ValueError("Stable ticket ID missing")
    if len(message_ids)!=len(plan.page_ranges) or any(type(m) is not int or m<1 for m in message_ids):
        raise ValueError("Telegram returned incomplete or invalid message IDs")
    if len(set(message_ids))!=len(message_ids):
        raise ValueError("Repeated Telegram message ID")
    return {"ticket_id":ticket_id,"chat_id":plan.data["chat_id"],
            "message_ids":list(message_ids),"page_ranges":[list(p) for p in plan.page_ranges],
            "sent_method":plan.method}


def plan_same_photo_settlement(ticket: dict, saved_state: dict, *,
                               master=MASTER_PATH, preview_only=False) -> list[TelegramPlan]:
    """Offline editMessageMedia plans that target ONLY the original photo IDs."""
    if not saved_state or not isinstance(saved_state.get("message_ids"),list):
        raise ValueError("No saved Telegram photo history")
    regenerated=plan_new_ticket(ticket,str(saved_state.get("chat_id") or ""),
                                master=master,preview_only=preview_only)
    ids=saved_state["message_ids"]
    if saved_state.get("page_ranges") != [list(p) for p in regenerated.page_ranges]:
        raise ValueError("Selection/page layout changed; old Telegram photo IDs must be preserved")
    if len(ids)!=len(regenerated.page_ranges):
        raise ValueError("Original photo count mismatch")
    edits=[]
    for i,message_id in enumerate(ids,1):
        if type(message_id) is not int or message_id<1:
            raise ValueError("Invalid saved photo message ID")
        filename,png,mimetype=(regenerated.files["photo"] if len(ids)==1 else regenerated.files[f"card_{i}"])
        media={"type":"photo","media":"attach://card"}
        plan=TelegramPlan("editMessageMedia",{
            "chat_id":regenerated.data["chat_id"],
            "message_id":str(message_id),"media":json.dumps(media)},
            {"card":(filename,png,mimetype)},(regenerated.page_ranges[i-1],))
        edits.append(plan)
    return edits