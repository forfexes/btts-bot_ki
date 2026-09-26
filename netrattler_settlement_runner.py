#!/usr/bin/env python3
"""Production entrypoint for settlement routing policy."""
from __future__ import annotations

import netrattler_settlement_v16_final as settlement


def install_routing() -> None:
    # User policy: 1X2 belongs to Telegram AI / main chat.
    # Goal Hunter/scorer remains in TELEGRAM_GROUP_LATE_GOALS.
    settlement.GROUPS["1x2"] = settlement.TG_DEFAULT


def main() -> None:
    install_routing()
    settlement.main()


if __name__ == "__main__":
    main()
