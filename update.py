import json
from datetime import datetime, timezone

try:
    from curl_cffi import requests
except ImportError:
    import requests

from bs4 import BeautifulSoup

TEAM_ID = 64295
TOURNAMENT_ID = 1015
BASES = [
    "https://www.sofascore.com/api/v1",
    "https://www.sofascore.com/api/v1",
    "https://api.sofascore.com/api/v1",
]
NEWS_URL = "https://www.persija.id/all-news"
OUT = "data.json"
ADV = "advanced.json"

HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}

# curl_cffi impersonates a real browser TLS fingerprint.
IMPERSONATE = "chrome131"

def get_json(url):
    last_error = None
    for base in BASES:
        candidate = url.replace("https://www.sofascore.com/api/v1", base, 1)
        try:
            r = requests.get(
                candidate,
                headers=HEADERS,
                timeout=25,
                impersonate=IMPERSONATE,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_error = e
            print(f"WARN {candidate} -> {e}")
    return None

def safe_json(url):
    d = get_json(url)
    return d if isinstance(d, dict) else None

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
            return value
    except Exception as e:
        print(f"WARN could not read {path}: {e}")
        return default

def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)

def latest_season(previous=None):
    urls = [
        f"{BASES[0]}/unique-tournament/{TOURNAMENT_ID}/seasons",
        f"{BASES[0]}/unique-tournament/{TOURNAMENT_ID}/seasons/last",
        f"{BASES[0]}/unique-tournament/{TOURNAMENT_ID}/seasons/previous/0",
    ]
    for url in urls:
        d = safe_json(url)
        seasons = (d or {}).get("seasons") or []
        if seasons:
            return seasons[0].get("id")
    print("WARN no SofaScore season available; keeping previous season.")
    return previous

def event_urls(kind, page):
    # Primary endpoint + alternate forms used by SofaScore deployments.
    return [
        f"{BASES[0]}/team/{TEAM_ID}/events/{kind}/{page}",
        f"{BASES[0]}/team/{TEAM_ID}/matches/{'previous' if kind == 'last' else 'next'}/{page}",
    ]

def get_matches(previous=None):
    out = {}
    successful = False

    for kind in ("last", "next"):
        for page in range(0, 3):
            d = None
            for url in event_urls(kind, page):
                d = safe_json(url)
                if d is not None and "events" in d:
                    successful = True
                    break

            if d is None:
                print(f"WARN unable to fetch {kind} page {page}; trying next page/endpoint.")
                continue

            for e in d.get("events") or []:
                h = e.get("homeTeam") or {}
                a = e.get("awayTeam") or {}
                if TEAM_ID not in (h.get("id"), a.get("id")) or not e.get("id"):
                    continue
                out[e["id"]] = {
                    "timestamp": e.get("startTimestamp"),
                    "home": h.get("name"),
                    "away": a.get("name"),
                    "home_score": (e.get("homeScore") or {}).get("current"),
                    "away_score": (e.get("awayScore") or {}).get("current"),
                    "venue": ((e.get("venue") or {}).get("name")
                              if isinstance(e.get("venue"), dict) else None),
                    "status": (e.get("status") or {}).get("type"),
                    "event_id": e.get("id"),
                }

            if not d.get("hasNextPage"):
                break

    matches = sorted(out.values(), key=lambda x: x.get("timestamp") or 0)
    if successful and matches:
        return matches
    print("WARN no fresh match data; keeping previous matches.")
    return previous if isinstance(previous, list) else []

def get_news(previous=None):
    try:
        r = requests.get(
            NEWS_URL,
            headers={"User-Agent": "Mozilla/5.0 (Persija Auto Update Bot)",
                     "Accept": "text/html,application/xhtml+xml"},
            timeout=25,
            impersonate=IMPERSONATE,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        items, seen = [], set()
        for a in soup.select('a[href*="/media/news/"]'):
            href = a.get("href")
            title = " ".join(a.stripped_strings)
            if not href or not title or href in seen or len(title) < 12:
                continue
            seen.add(href)
            if href.startswith("/"):
                href = "https://www.persija.id" + href
            items.append({
                "title": title,
                "summary": "Berita terbaru Persija.",
                "date": None,
                "url": href,
                "tag": "NEWS",
            })
            if len(items) >= 12:
                break
        if items:
            return items
    except Exception as e:
        print(f"WARN news fetch failed: {e}")

    print("WARN no fresh news; keeping previous news.")
    return previous if isinstance(previous, list) else []

def get_standings(season, previous=None):
    if not season:
        print("WARN no season; keeping previous standings.")
        return previous if isinstance(previous, list) else []

    urls = [
        f"{BASES[0]}/unique-tournament/{TOURNAMENT_ID}/season/{season}/standings/total",
        f"{BASES[0]}/unique-tournament/{TOURNAMENT_ID}/season/{season}/standings/overall",
    ]

    for url in urls:
        d = safe_json(url)
        standings = (d or {}).get("standings") or []
        if not standings:
            continue

        rows = standings[0].get("rows") or []
        result = []
        for r in rows:
            t = r.get("team") or {}
            result.append({
                "position": r.get("position"),
                "team": t.get("name"),
                "team_id": t.get("id"),
                "matches": r.get("matches", 0),
                "gd": (r.get("scoresFor", 0) - r.get("scoresAgainst", 0)),
                "points": r.get("points", 0),
            })
        if result:
            return result

    print("WARN no fresh standings; keeping previous standings.")
    return previous if isinstance(previous, list) else []

def get_live_event(matches, previous=None):
    # Avoid replacing a previously known live event with empty data on API failure.
    for m in matches:
        event_id = m.get("event_id")
        if not event_id:
            continue
        d = safe_json(f"{BASES[0]}/event/{event_id}")
        if not d:
            continue
        status = d.get("status") or {}
        if status.get("type") == "inprogress":
            return build_event_detail(m, d)
    return previous if isinstance(previous, dict) else None

def build_event_detail(m, event):
    event_id = m["event_id"]
    hs = (event.get("homeScore") or {}).get("current")
    aws = (event.get("awayScore") or {}).get("current")
    st = event.get("status") or {}
    stats = []

    sd = safe_json(f"{BASES[0]}/event/{event_id}/statistics") or {}
    blocks = sd.get("statistics") or []
    if blocks:
        period = blocks[-1] if isinstance(blocks, list) else blocks
        for group in period.get("groups", []):
            for item in group.get("statisticsItems", []):
                if item.get("name") in ("Ball possession", "Shots on target",
                                         "Corner kicks", "Total shots"):
                    stats.append({
                        "label": item.get("name"),
                        "value": f"{item.get('home', '-')} - {item.get('away', '-')}",
                    })

    return {
        "event_id": event_id,
        "home": (event.get("homeTeam") or {}).get("name"),
        "away": (event.get("awayTeam") or {}).get("name"),
        "home_score": hs,
        "away_score": aws,
        "is_live": True,
        "status_text": st.get("description") or "LIVE",
        "stats": stats,
    }

def get_form(matches, previous=None):
    vals = []
    for m in matches:
        if m.get("status") != "finished":
            continue
        hs, away_score = m.get("home_score"), m.get("away_score")
        if hs is None or away_score is None:
            continue
        persija_home = m.get("home") == "Persija Jakarta"
        pf, pa = (hs, away_score) if persija_home else (away_score, hs)
        vals.append({
            "result": "W" if pf > pa else "D" if pf == pa else "L",
            "opponent": m.get("away") if persija_home else m.get("home"),
        })
    return vals[-5:] if vals else (previous if isinstance(previous, list) else [])

def get_scorers(matches, previous=None):
    tally = {}
    had_success = False
    for m in matches:
        if m.get("status") != "finished" or not m.get("event_id"):
            continue
        d = safe_json(f"{BASES[0]}/event/{m['event_id']}/incidents")
        if d is None:
            continue
        had_success = True
        for x in d.get("incidents") or []:
            if x.get("incidentType") != "goal" or x.get("incidentClass") in ("missed", "ownGoal"):
                continue
            team = (m.get("home") if x.get("isHome") else m.get("away"))
            if team != "Persija Jakarta":
                continue
            name = (x.get("player") or {}).get("name")
            if name:
                tally[name] = tally.get(name, 0) + 1

    result = [{"name": n, "goals": g}
              for n, g in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:8]]
    if result or had_success:
        return result
    print("WARN no fresh scorer data; keeping previous scorers.")
    return previous if isinstance(previous, list) else []

def main():
    old_data = load_json(OUT, {})
    old_adv = load_json(ADV, {})

    previous_matches = old_data.get("matches", [])
    previous_news = old_data.get("news", [])
    previous_season = old_adv.get("season")

    matches = get_matches(previous_matches)
    season = latest_season(previous_season)

    # Only replace fields when fresh data is available.
    updated_at = datetime.now(timezone.utc).isoformat()
    data = dict(old_data) if isinstance(old_data, dict) else {}
    data["updated_at"] = updated_at
    data["source"] = {
        "news": NEWS_URL,
        "matches": f"{BASES[0]}/team/{TEAM_ID}/events/next/0",
        "standings": (f"{BASES[0]}/unique-tournament/{TOURNAMENT_ID}/"
                      f"season/{season}/standings/total" if season else old_adv.get("source")),
    }
    data["news"] = get_news(previous_news)
    data["matches"] = matches

    old_standings = old_adv.get("standings", [])
    old_form = old_adv.get("form", [])
    old_scorers = old_adv.get("scorers", [])
    old_live = old_adv.get("live_event")

    adv = dict(old_adv) if isinstance(old_adv, dict) else {}
    adv["updated_at"] = updated_at
    adv["season"] = season if season is not None else previous_season
    adv["standings"] = get_standings(season, old_standings)
    adv["form"] = get_form(matches, old_form)
    adv["scorers"] = get_scorers(matches, old_scorers)
    adv["live_event"] = get_live_event(matches, old_live)

    write_json(OUT, data)
    write_json(ADV, adv)
    print("OK:", OUT, "and", ADV, "written without crashing.")

if __name__ == "__main__":
    main()
