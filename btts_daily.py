def fetch_next_fixtures():
    if not API_FOOTBALL_KEY:
        log("API_FOOTBALL_KEY fehlt")
        return []

    headers = {
        "x-apisports-key": API_FOOTBALL_KEY
    }

    try:
        # NÄCHSTE SPIELE + HEUTE KOMBINIEREN
        fixtures = []

        # 1. nächste Spiele
        r1 = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=headers,
            params={"next": 50},
            timeout=20,
        )

        # 2. heute
        today = datetime.now().strftime("%Y-%m-%d")
        r2 = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers=headers,
            params={"date": today},
            timeout=20,
        )

        data = []
        if r1.ok:
            data += r1.json().get("response", [])
        if r2.ok:
            data += r2.json().get("response", [])

        results = []

        for item in data:
            teams = item.get("teams", {})
            league = item.get("league", {})

            home = teams.get("home", {}).get("name")
            away = teams.get("away", {}).get("name")

            if not home or not away:
                continue

            results.append({
                "league": league.get("name"),
                "country": league.get("country"),
                "home": home,
                "away": away,
            })

        return results

    except Exception as e:
        log(f"API Fehler: {e}")
        return []
