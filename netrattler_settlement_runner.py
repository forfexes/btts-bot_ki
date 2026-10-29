#!/usr/bin/env python3
"""Production entrypoint for settlement routing policy."""
from __future__ import annotations

import netrattler_settlement_v16_final as settlement


def install_routing() -> None:
    # 1X2 belongs to Telegram AI / main chat.
    settlement.GROUPS["1x2"] = settlement.TG_DEFAULT
    # BTTS HT and O1.5 HT intentionally share the same Telegram group.
    settlement.GROUPS["over15_ht"] = settlement.GROUPS.get("btts_ht") or settlement.TG_DEFAULT
    # All grading belongs inside the original tip, never in a separate report.
    settlement.send_group_reports = lambda *_args: None
    settlement.send_roi_report = lambda _history: None


def main() -> None:
    install_routing()
    settlement.main()


if __name__ == "__main__":
    main()
