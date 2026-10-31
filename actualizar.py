"""Actualiza calendario y promedios observados de los últimos 30 días.
Fuente pública no oficial de ESPN; puede cambiar o limitar solicitudes.
"""
import datetime as dt
import json
import os
import time
import urllib.request
from pathlib import Path

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
ROOT = Path(__file__).resolve().parent
TZ = dt.timezone(dt.timedelta(hours=-6))
TODAY = dt.datetime.now(TZ).date()

def get(path):
    req = urllib.request.Request(BASE + path, headers={'User-Agent': 'Mozilla/5.0 (NBA personal dashboard)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)

def code(team):
    return team.get('abbreviation', '').upper()

def main():
    games = {}
    for days in range(-30, 2):
        date = TODAY + dt.timedelta(days=days)
        data = get('/scoreboard?dates=' + date.strftime('%Y%m%d') + '&limit=100')
        for event in data.get('events', []):
            games[event['id']] = event
        time.sleep(.08)
    matchups = {}
    totals = {}
    for event in games.values():
        comps = (event.get('competitions') or [{}])[0].get('competitors') or []
        if len(comps) != 2:
            continue
        home = next((x for x in comps if x.get('homeAway') == 'home'), None)
        away = next((x for x in comps if x.get('homeAway') == 'away'), None)
        if not home or not away:
            continue
        h, a = code(home.get('team', {})), code(away.get('team', {}))
        if event.get('date', '')[:10] in {TODAY.isoformat(), (TODAY + dt.timedelta(days=1)).isoformat()}:
            matchups[h] = [a, 1]
            matchups[a] = [h, 0]
        if event.get('status', {}).get('type', {}).get('completed') is not True:
            continue
        try:
            detail = get('/summary?event=' + event['id'])
        except Exception as exc:
            print('Partido omitido:', event['id'], exc)
            continue
        for team in detail.get('boxscore', {}).get('players', []):
            abbr = code(team.get('team', {}))
            for group in team.get('statistics', []):
                keys = [str(x).lower() for x in group.get('keys', [])]
                for athlete in group.get('athletes', []):
                    values = athlete.get('stats') or []
                    if not values or athlete.get('didNotPlay'):
                        continue
                    raw = dict(zip(keys, values))
                    try:
                        pts = float(raw.get('points', raw.get('pts')))
                        reb = float(raw.get('rebounds', raw.get('reb')))
                        ast = float(raw.get('assists', raw.get('ast')))
                        minutes = raw.get('minutes', raw.get('min', '0'))
                        minutes = float(minutes.split(':')[0]) + float(minutes.split(':')[1])/60 if ':' in str(minutes) else float(minutes)
                    except (TypeError, ValueError):
                        continue
                    ident = athlete.get('athlete', {}).get('id')
                    if not ident or minutes <= 0:
                        continue
                    key = str(ident)
                    obj = totals.setdefault(key, {'name': athlete.get('athlete', {}).get('displayName', ''), 'team': abbr, 'games': 0, 'minutes': 0, 'pts': 0, 'reb': 0, 'ast': 0})
                    obj['team'] = abbr
                    obj['games'] += 1
                    for k, v in [('minutes', minutes), ('pts', pts), ('reb', reb), ('ast', ast)]:
                        obj[k] += v
        time.sleep(.1)
    players = []
    for obj in totals.values():
        n = obj['games']
        if n:
            players.append({'name': obj['name'], 'team': obj['team'], 'games': n, 'minutes': round(obj['minutes']/n, 2), 'pts': round(obj['pts']/n, 2), 'reb': round(obj['reb']/n, 2), 'ast': round(obj['ast']/n, 2)})
    if not games or not players:
        raise RuntimeError('No se obtuvieron estadísticas válidas. Se conserva el archivo anterior.')
    result = {'updated': dt.datetime.now(dt.timezone.utc).isoformat(), 'date': TODAY.isoformat(), 'window': 'Últimos 30 días (partidos disponibles)', 'matchups': matchups, 'players': players}
    target = ROOT / 'datos.json'
    temp = ROOT / 'datos.tmp'
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, target)
    print('Actualizado:', len(players), 'jugadores,', len(matchups)//2, 'partidos próximos')

if __name__ == '__main__':
    main()
