#!/usr/bin/env python3
"""
NETRATTLER Settlement Wrapper
Startet die Settlement-Engine aus btts_bot.py.

Warum eigene Datei?
GitHub Workflow kann `python settlement.py` starten,
während die eigentliche Logik weiterhin in btts_bot.py liegt.
"""

import sys
import traceback

try:
    import btts_bot
except Exception as e:
    print(f"❌ Import btts_bot fehlgeschlagen: {e}")
    print(traceback.format_exc())
    sys.exit(1)


def main():
    if not hasattr(btts_bot, "run_settlement"):
        print("❌ run_settlement() nicht in btts_bot.py gefunden")
        sys.exit(1)

    print("⚽ NETRATTLER Settlement startet...")
    btts_bot.run_settlement()
    print("✅ NETRATTLER Settlement fertig")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Settlement Fatal: {e}")
        print(traceback.format_exc())
        sys.exit(1)
