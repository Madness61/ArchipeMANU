"""Pure, spoiler-free calculations from observed WebHost tracker responses."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def number(value, minimum=0):
    return value if type(value) is int and value >= minimum else None


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        date = parsedate_to_datetime(value)
        return date.replace(tzinfo=date.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def indexed(data, field):
    rows = data.get(field)
    if not isinstance(rows, list):
        return {}
    return {(r["team"], r["player"]): r for r in rows
            if isinstance(r, dict) and number(r.get("team")) is not None
            and number(r.get("player"), 1) is not None}


def key(pair):
    return f"{pair[0]}:{pair[1]}"


def percent(done, total):
    return round(100 * done / total, 1) if done is not None and total else None


def aggregate(room, static, dynamic):
    games = indexed(static, "player_game")
    if not games or not indexed(dynamic, "player_checks_done"):
        raise ValueError("Tracker noch nicht verfügbar oder unvollständiges API-Format.")
    if not all(isinstance(entry.get("game"), str) and entry["game"] for entry in games.values()):
        raise ValueError("Spielzuordnung des Trackers ist unvollständig.")
    fields = {f: indexed(dynamic, f) for f in ("aliases", "player_checks_done", "player_items_received",
                                             "player_status", "activity_timers", "connection_timers")}
    totals = indexed(static, "player_locations_total")
    # Name-only room lists have no slot IDs. Only use their order when every
    # participating ID is contiguous and each game's name agrees.
    room_players = room.get("players", [])
    names = {}
    ids = sorted({p for _, p in games})
    if (isinstance(room_players, list) and ids == list(range(1, len(room_players) + 1))
            and all(isinstance(row, list) and len(row) >= 2 for row in room_players)
            and all(room_players[p - 1][1] == game.get("game") for (_, p), game in games.items())):
        names = {i + 1: str(row[0])[:80] for i, row in enumerate(room_players)}
    players, checked = [], {}
    for pair, entry in sorted(games.items()):
        locations = fields["player_checks_done"].get(pair, {}).get("locations")
        checked[pair] = (set(locations) if isinstance(locations, list)
                         and all(type(v) is int for v in locations) else None)
        done = len(checked[pair]) if checked[pair] is not None else None
        total = number(totals.get(pair, {}).get("total_locations"))
        status = number(fields["player_status"].get(pair, {}).get("status"))
        alias = fields["aliases"].get(pair, {}).get("alias")
        name = alias[:80] if isinstance(alias, str) and alias else names.get(pair[1], f"Slot {pair[1]}")
        items = fields["player_items_received"].get(pair, {}).get("items")
        valid_items = [v for v in items if isinstance(v, (list, tuple)) and len(v) >= 4
                       and all(type(n) is int for n in v[:4])] if isinstance(items, list) else None
        if valid_items is not None and len(valid_items) != len(items):
            valid_items = None
        categories = Counter()
        for item in valid_items or []:
            categories["progression" if item[3] & 1 else "useful" if item[3] & 2
                       else "trap" if item[3] & 4 else "filler"] += 1
        players.append(dict(key=key(pair), team=pair[0], slot=pair[1], name=name,
                            game=str(entry.get("game", "Unbekannt"))[:120], checks=done, total=total,
                            progress=percent(done, total), received=len(valid_items) if valid_items is not None else None,
                            goal=(status == 30) if status is not None else None,
                            status=status, categories=dict(categories) if valid_items is not None else None,
                            activity=stamp(fields["activity_timers"].get(pair, {}).get("time")),
                            connection=stamp(fields["connection_timers"].get(pair, {}).get("time")),
                            own_items=0, foreign_items=0))
    by_key = {p["key"]: p for p in players}
    edges = Counter()
    seen = set()
    for pair, received in fields["player_items_received"].items():
        recipient = key(pair)
        if recipient not in by_key or not isinstance(received.get("items"), list):
            continue
        for item in received["items"]:
            if not isinstance(item, (list, tuple)) or len(item) < 4 or not all(type(v) is int for v in item[:4]):
                continue
            _, location, sender, _ = item[:4]
            finder_pair = (pair[0], sender)
            finder = key(finder_pair)
            identity = (recipient, finder, location)
            # Starting inventory, cheats, item-link group deliveries and records
            # without a matching observed check cannot be attributed reliably.
            if (location <= 0 or finder not in by_key or checked.get(finder_pair) is None
                    or location not in checked[finder_pair] or identity in seen):
                continue
            seen.add(identity)
            edges[finder, recipient] += 1
            by_key[recipient]["own_items" if finder == recipient else "foreign_items"] += 1
    for player in players:
        player["sent_to_others"] = sum(n for (finder, recipient), n in edges.items()
                                        if finder == player["key"] and recipient != finder)
        player["unattributed"] = (max(0, player["received"] - player["own_items"] - player["foreign_items"])
                                  if player["received"] is not None else None)
    def total_of(field):
        return sum(p[field] for p in players) if all(p[field] is not None for p in players) else None
    done, total = total_of("checks"), total_of("total")
    interactions_available = all(p["received"] is not None and p["checks"] is not None for p in players)
    if not interactions_available:
        for player in players:
            for field in ("own_items", "foreign_items", "sent_to_others", "unattributed"):
                player[field] = None
    goals = sum(p["goal"] for p in players if p["goal"] is not None)
    return dict(players=players, checks=done, total=total, progress=percent(done, total),
                received=total_of("received"), goals=goals,
                known_goals=sum(p["goal"] is not None for p in players),
                games=len({p["game"] for p in players}), player_count=len(players),
                average_progress=(round(sum(p["progress"] for p in players) / len(players), 1)
                                  if all(p["progress"] is not None for p in players) else None),
                interactions=([dict(finder=f, recipient=r, count=n) for (f, r), n in sorted(edges.items())]
                              if interactions_available else None),
                attributed=sum(edges.values()) if interactions_available else None,
                foreign=sum(n for (f, r), n in edges.items() if f != r) if interactions_available else None,
                own=sum(n for (f, r), n in edges.items() if f == r) if interactions_available else None)


def history_point(data):
    fields = ("key", "name", "game", "checks", "total", "progress", "received", "goal", "status")
    return {**{k: data[k] for k in ("checks", "total", "progress", "received", "goals", "known_goals")},
            "players": [{k: p[k] for k in fields} for p in data["players"]]}


def changes(previous, current):
    """An observation time is not an in-game event time; never backfill events."""
    if previous is None:
        return [dict(kind="start", player=None, text="Die Live-Aufzeichnung hat begonnen.")], False
    old = {p["key"]: p for p in previous["players"]}
    reset = any(p["checks"] is not None and old.get(p["key"], {}).get("checks") is not None
                and p["checks"] < old[p["key"]]["checks"] for p in current["players"])
    if reset:
        return [dict(kind="reset", player=None,
                     text="Der Tracker meldet weniger Checks. Ein neuer Verlaufabschnitt beginnt.")], True
    events = []
    for player in current["players"]:
        before = old.get(player["key"])
        if before is None:
            continue
        def event(kind, text):
            events.append(dict(kind=kind, player=player["key"], text=f"{player['name']}: {text}"))
        for field, kind, label in (("checks", "checks", "weitere Checks"), ("received", "items", "weitere Items gemeldet")):
            if player[field] is not None and before[field] is not None and player[field] > before[field]:
                event(kind, f"{player[field] - before[field]} {label}.")
        if player["goal"] and before["goal"] is False:
            event("goal", "Ziel vom Spielclient als erreicht gemeldet.")
        if player["status"] != before["status"] and player["status"] is not None:
            event("status", "Der gemeldete Clientstatus hat sich geändert.")
        if player["progress"] is not None and before["progress"] is not None:
            for threshold in (25, 50, 75, 100):
                if before["progress"] < threshold <= player["progress"]:
                    event("milestone", f"{threshold} % der Checks erreicht.")
    return events, False
