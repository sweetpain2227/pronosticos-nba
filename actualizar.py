"""Actualiza estadísticas NBA y próximos partidos desde ESPN (fuente no oficial)."""
import datetime as dt
import json
import os
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ROOT = Path(__file__).resolve().parent
TZ = ZoneInfo("America/Merida")
ALIASES = {"NO": "NOP", "NY": "NYK", "GS": "GSW", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS", "PHO": "PHX", "BRK": "BKN", "CHO": "CHA"}

def get(path, attempts=3):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(1.5 * (attempt + 1))

def code(team):
    value = str((team or {}).get("abbreviation", "")).upper()
    return ALIASES.get(value, value)

def parse_time(value):
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

def numeric(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def minutes_value(value):
    if value is None:
        return None
    if ":" in str(value):
        a, b = str(value).split(":", 1)
        return float(a) + float(b) / 60
    return numeric(value)

def main():
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(TZ).date()
    games = {}
    failed_dates = []
    # Últimos 30 días para promedios; próximos 10 días para el calendario.
    for days in range(-30, 11):
        date = today + dt.timedelta(days=days)
        try:
            data = get("/scoreboard?dates=" + date.strftime("%Y%m%d") + "&limit=100")
            for event in data.get("events", []):
                if event.get("id"):
                    games[str(event["id"])] = event
        except Exception as exc:
            failed_dates.append(date.isoformat())
            print("Advertencia: fecha omitida", date, exc)
        time.sleep(.06)
    totals = {}
    upcoming = {}
    for event in games.values():
        comps = ((event.get("competitions") or [{}])[0].get("competitors") or [])
        home = next((x for x in comps if x.get("homeAway") == "home"), None)
        away = next((x for x in comps if x.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        h, a = code(home.get("team")), code(away.get("team"))
        if not h or not a:
            continue
        event_time = parse_time(event.get("date"))
        status = event.get("status", {}).get("type", {})
        completed = status.get("completed") is True
        state = status.get("state", "")
        if not completed and event_time and (event_time >= now - dt.timedelta(hours=5)):
            # No usar encuentros finalizados; elegir el siguiente por fecha.
            phase = "live" if state == "in" else "scheduled"
            for team, opponent, is_home in ((h, a, 1), (a, h, 0)):
                item = {"opponent": opponent, "home": is_home, "start": event_time.isoformat(), "status": phase, "event_id": str(event["id"])}
                if team not in upcoming or item["start"] < upcoming[team]["start"]:
                    upcoming[team] = item
        if not completed:
            continue
        try:
            detail = get("/summary?event=" + str(event["id"]))
        except Exception as exc:
            print("Advertencia: boxscore omitido", event["id"], exc)
            continue
        for team in detail.get("boxscore", {}).get("players", []):
            abbr = code(team.get("team"))
            for group in team.get("statistics", []):
                keys = [str(x).lower() for x in group.get("keys", [])]
                for athlete in group.get("athletes", []):
                    if athlete.get("didNotPlay"):
                        continue
                    raw = dict(zip(keys, athlete.get("stats") or []))
                    pts = numeric(raw.get("points", raw.get("pts")))
                    reb = numeric(raw.get("rebounds", raw.get("reb")))
                    ast = numeric(raw.get("assists", raw.get("ast")))
                    mins = minutes_value(raw.get("minutes", raw.get("min")))
                    identity = athlete.get("athlete") or {}
                    if any(x is None for x in (pts, reb, ast, mins)) or mins <= 0 or not identity.get("id"):
                        continue
                    key = str(identity["id"])
                    obj = totals.setdefault(key, {"id": key, "name": identity.get("displayName", ""), "team": abbr, "games": 0, "minutes": 0, "pts": 0, "reb": 0, "ast": 0})
                    obj["team"] = abbr
                    obj["games"] += 1
                    for stat, value in (("minutes", mins), ("pts", pts), ("reb", reb), ("ast", ast)):
                        obj[stat] += value
        time.sleep(.08)
    players = []
    for obj in totals.values():
        n = obj["games"]
        if n:
            players.append({"id": obj["id"], "name": obj["name"], "team": obj["team"], "games": n, "minutes": round(obj["minutes"] / n, 2), "pts": round(obj["pts"] / n, 2), "reb": round(obj["reb"] / n, 2), "ast": round(obj["ast"] / n, 2)})
    if len(players) < 30:
        raise RuntimeError("Se recibieron muy pocos jugadores. Se conserva datos.json anterior.")
    result = {"updated": now.isoformat(), "date": today.isoformat(), "window": "Últimos 30 días (partidos disponibles)", "matchups": {k: [v["opponent"], v["home"]] for k, v in upcoming.items()}, "games": upcoming, "players": players, "warnings": {"dates_failed": failed_dates}}
    tmp = ROOT / "datos.tmp"
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ROOT / "datos.json")
    print("Actualizado:", len(players), "jugadores;", len(upcoming) // 2, "próximos partidos;", len(failed_dates), "fechas omitidas")

if __name__ == "__main__":
    main()
