"""
PRIORITY QUEUE FÜR SPIELE - VERHINDERT VERSPÄTETE TIPPS
Sortiert Spiele nach Start-Zeit und verarbeitet die soonest first!
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Callable
from heapq import heappush, heappop

class MatchPriorityQueue:
    def __init__(self):
        self.queue = []
        self.processed = set()
    
    def add_match(self, match: Dict):
        """
        Sortiert Match nach Start-Zeit (früher = höhere Priorität)
        
        Args:
            match: Dict mit 'fixture_date', 'home', 'away', 'league', etc.
        """
        
        # Parse Start-Zeit
        try:
            start_time = datetime.fromisoformat(match["fixture_date"].replace("Z", "+00:00"))
        except:
            start_time = datetime.now(timezone.utc)
        
        # Timestamp (float) für Heap
        priority = start_time.timestamp()
        
        # Verhindere Duplikate
        match_id = f"{match.get('home')}_{match.get('away')}_{match.get('fixture_date')}"
        if match_id not in self.processed:
            heappush(self.queue, (priority, match_id, match))
            self.processed.add(match_id)
    
    def get_urgent_matches(self, minutes_ahead: int = 120) -> List[Dict]:
        """
        Holt alle Spiele die in den nächsten N Minuten starten
        
        Args:
            minutes_ahead: Fenster (Standard: 120 Min)
        
        Returns:
            Liste sortiert nach Dringlichkeit
        """
        now = datetime.now(timezone.utc).timestamp()
        deadline = now + (minutes_ahead * 60)
        
        urgent = []
        while self.queue:
            priority, match_id, match = self.queue[0]
            
            if priority <= deadline:
                heappop(self.queue)
                urgent.append(match)
            else:
                break
        
        return urgent
    
    def get_next(self) -> Dict | None:
        """Nächstes Spiel aus der Queue"""
        if self.queue:
            priority, match_id, match = heappop(self.queue)
            return match
        return None
    
    def size(self) -> int:
        return len(self.queue)


async def process_matches_parallel(
    matches: List[Dict],
    processor_func: Callable,
    max_concurrent: int = 5
) -> List[Dict]:
    """
    Verarbeitet mehrere Matches gleichzeitig (NICHT sequenziell!)
    
    Args:
        matches: Liste Matches
        processor_func: async Funktion die ein Match verarbeitet
        max_concurrent: Max 5 parallele Requests (API-Rate-Limit respektieren)
    
    Returns:
        Tipps in Reihenfolge (nach Priorität)
    """
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def bounded_processor(match):
        async with semaphore:
            return await processor_func(match)
    
    # Starte alle Tasks gleichzeitig (aber begrenzt)
    tasks = [bounded_processor(m) for m in matches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter Errors
    tips = [r for r in results if r and not isinstance(r, Exception)]
    
    return tips


# BEISPIEL INTEGRATION in btts_daily_extended.py

async def process_matches_with_priority(matches: List[Dict], api_keys: Dict) -> List[Dict]:
    """
    Neue Pipeline:
    1. Sortiere Matches nach Start-Zeit
    2. Verarbeite PARALLELE statt sequenziell
    3. Gebe Tipps SOFORT raus (statt Ende der Nacht)
    """
    
    queue = MatchPriorityQueue()
    
    # Füge alle Spiele hinzu
    for match in matches:
        queue.add_match(match)
    
    # Hol nur Spiele in den nächsten 2h (zu früh = aussortiert)
    urgent_matches = queue.get_urgent_matches(minutes_ahead=120)
    
    print(f"[PRIORITY] {len(urgent_matches)} Spiele in den nächsten 2 Stunden")
    
    # Importiere async processor aus btts_daily_extended
    # (musst du noch umschreiben auf async)
    
    # Verarbeite parallel
    tips = await process_matches_parallel(
        urgent_matches,
        processor_func=analyze_match_async,  # Siehe unten
        max_concurrent=5
    )
    
    print(f"[PRIORITY] {len(tips)} Tipps generiert")
    
    return tips


async def analyze_match_async(match: Dict) -> Dict:
    """
    Async Version von match-Analysis (statt blocking requests)
    Würde in btts_daily_extended.py als async umgeschrieben
    """
    
    # TODO: Convert analyze_match() zu async mit asyncio.gather()
    # für alle API-Calls gleichzeitig
    
    pass
