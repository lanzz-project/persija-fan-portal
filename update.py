import json, re, requests
from datetime import datetime, timezone

TEAM_ID = 64295
TOURNAMENT_ID = 1015  # Indonesia Super League
BASE = "https://www.sofascore.com/api/v1"
NEWS_URL = "https://www.persija.id/all-news"
OUT = "data.json"
ADV = "advanced.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Persija Auto Update Bot)",
    "Accept": "application/json,text/html"
}

def get_json(url):
    r=requests.get(url,headers=HEADERS,timeout=25)
    r.raise_for_status()
    return r.json()

def safe_json(url, fallback):
    try: return get_json(url)
    except Exception as e:
        print("WARN", url, e); return fallback

def latest_season():
    d=safe_json(f"{BASE}/unique-tournament/{TOURNAMENT_ID}/seasons",{"seasons":[]})
    return d.get("seasons",[{}])[0].get("id")

def get_matches():
    out={}
    for kind in ("last","next"):
        for page in range(0,3):
            d=safe_json(f"{BASE}/team/{TEAM_ID}/events/{kind}/{page}",{"events":[]})
            for e in d.get("events",[]):
                h=e.get("homeTeam",{}); a=e.get("awayTeam",{})
                if TEAM_ID not in (h.get("id"),a.get("id")): continue
                out[e["id"]]={
                    "timestamp":e.get("startTimestamp"),
                    "home":h.get("name"),"away":a.get("name"),
                    "home_score":(e.get("homeScore") or {}).get("current"),
                    "away_score":(e.get("awayScore") or {}).get("current"),
                    "venue":((e.get("venue") or {}).get("name") if isinstance(e.get("venue"),dict) else None),
                    "status":(e.get("status") or {}).get("type"),
                    "event_id":e.get("id")
                }
            if not d.get("hasNextPage"): break
    return sorted(out.values(),key=lambda x:x.get("timestamp") or 0)

def get_news():
    from bs4 import BeautifulSoup
    r=requests.get(NEWS_URL,headers=HEADERS,timeout=25); r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    items=[]; seen=set()
    for a in soup.select('a[href*="/media/news/"]'):
        href=a.get("href"); title=" ".join(a.stripped_strings)
        if not href or not title or href in seen or len(title)<12: continue
        seen.add(href)
        if href.startswith("/"): href="https://www.persija.id"+href
        items.append({"title":title,"summary":"Berita terbaru Persija.","date":None,"url":href,"tag":"NEWS"})
        if len(items)>=12: break
    return items

def get_standings(season):
    if not season: return []
    d=safe_json(f"{BASE}/unique-tournament/{TOURNAMENT_ID}/season/{season}/standings/total",{"standings":[]})
    rows=(d.get("standings") or [{}])[0].get("rows",[])
    result=[]
    for r in rows:
        t=r.get("team") or {}
        result.append({"position":r.get("position"),"team":t.get("name"),"team_id":t.get("id"),
                        "matches":r.get("matches",0),"gd":r.get("scoresFor",0)-r.get("scoresAgainst",0),
                        "points":r.get("points",0)})
    return result

def get_live_event(matches):
    # Prefer live, otherwise return None.
    for m in matches:
        e=safe_json(f"{BASE}/event/{m['event_id']}",{})
        status=e.get("status") or {}
        if status.get("type")=="inprogress":
            return build_event_detail(m)
    return None

def build_event_detail(m):
    e=safe_json(f"{BASE}/event/{m['event_id']}",{})
    hs=(e.get("homeScore") or {}).get("current")
    aws=(e.get("awayScore") or {}).get("current")
    st=e.get("status") or {}
    stats=[]
    sd=safe_json(f"{BASE}/event/{m['event_id']}/statistics",{"statisticsItems":[]})
    blocks=sd.get("statistics") or []
    if blocks:
        period=(blocks[-1] if isinstance(blocks,list) else blocks)
        for group in period.get("groups",[]):
            for item in group.get("statisticsItems",[]):
                if item.get("name") in ("Ball possession","Shots on target","Corner kicks","Total shots"):
                    stats.append({"label":item.get("name"),"value":f"{item.get('home','-')} - {item.get('away','-')}"})
    return {"event_id":m["event_id"],"home":e.get("homeTeam",{}).get("name"),"away":e.get("awayTeam",{}).get("name"),
            "home_score":hs,"away_score":aws,"is_live":True,"status_text":st.get("description") or "LIVE","stats":stats}

def get_form(matches):
    vals=[]
    for m in matches:
        if m.get("status")!="finished": continue
        hs,as_=m.get("home_score"),m.get("away_score")
        if hs is None or as_ is None: continue
        persija_home=m["home"]=="Persija Jakarta"
        pf,pa=(hs,as_) if persija_home else (as_,hs)
        vals.append({"result":"W" if pf>pa else "D" if pf==pa else "L","opponent":m["away"] if persija_home else m["home"]})
    return vals[-5:]

def get_scorers(matches):
    # Derive a lightweight recent-form scorer board from match incidents.
    tally={}
    for m in matches:
        if m.get("status")!="finished": continue
        d=safe_json(f"{BASE}/event/{m['event_id']}/incidents",{"incidents":[]})
        for x in d.get("incidents",[]):
            if x.get("incidentType")!="goal" or x.get("incidentClass")=="missed": continue
            if x.get("incidentClass")=="ownGoal": continue
            team=(x.get("isHome") and m["home"]) or m["away"]
            if team!="Persija Jakarta": continue
            name=(x.get("player") or {}).get("name")
            if name: tally[name]=tally.get(name,0)+1
    return [{"name":n,"goals":g} for n,g in sorted(tally.items(),key=lambda kv:(-kv[1],kv[0]))[:8]]

def main():
    matches=get_matches()
    season=latest_season()
    data={
        "updated_at":datetime.now(timezone.utc).isoformat(),
        "source":{"news":NEWS_URL,"matches":f"{BASE}/team/{TEAM_ID}/events/next/0","standings":f"{BASE}/unique-tournament/{TOURNAMENT_ID}/season/{season}/standings/total"},
        "news":get_news(),
        "matches":matches
    }
    with open(OUT,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)

    adv={
        "updated_at":data["updated_at"],
        "season":season,
        "standings":get_standings(season),
        "form":get_form(matches),
        "scorers":get_scorers(matches),
        "live_event":get_live_event(matches)
    }
    with open(ADV,"w",encoding="utf-8") as f: json.dump(adv,f,ensure_ascii=False,indent=2)
    print("Updated",OUT,ADV)

if __name__=="__main__": main()
