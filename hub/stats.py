"""Deterministic aggregation of *real* placed Archipelago items.

Only call this with placements from a successfully generated MultiWorld.
No synthetic values, no importing/pickling uploaded seed archives.
"""

def valid_distribution(data):
    """Accept only complete, internally consistent generator statistics."""
    if not isinstance(data, dict) or data.get("source") != "archipelago_generated_multiworld":
        return False
    try:
        players = data["players"]
        if not isinstance(players, list) or not players:
            return False
        if any(type(p["id"]) is not int or p["id"] < 1
               or not isinstance(p["name"], str) or not isinstance(p["game"], str) for p in players):
            return False
        ids = [str(p["id"]) for p in players]
        if len(set(ids)) != len(ids):
            return False
        keys = set(ids)
        for field in ("matrix", "categories", "location_totals", "recipient_totals"):
            if not isinstance(data[field], dict) or set(data[field]) != keys:
                return False
        total = crossworld = 0
        for finder in ids:
            row = data["matrix"][finder]
            if not isinstance(row, dict) or set(row) != keys:
                return False
            if any(type(n) is not int or n < 0 for n in row.values()):
                return False
            if data["location_totals"][finder] != sum(row.values()):
                return False
            total += sum(row.values())
            crossworld += sum(n for recipient, n in row.items() if recipient != finder)
        for recipient in ids:
            counts = data["categories"][recipient]
            if not isinstance(counts, dict) or set(counts) != {"progression", "useful", "trap", "filler"}:
                return False
            if any(type(n) is not int or n < 0 for n in counts.values()):
                return False
            received = sum(data["matrix"][finder][recipient] for finder in ids)
            if received != sum(counts.values()) or data["recipient_totals"][recipient] != received:
                return False
        return (data["total_placements"] == total
                and data["crossworld_placements"] == crossworld
                and data["crossworld_percent"] == (round(crossworld * 100 / total, 1) if total else 0))
    except (KeyError, TypeError):
        return False


def aggregate_placements(players, placements):
    """players: [{id, name, game}]; placements: (finder_id, recipient_id, category)."""
    ordered = list(players)
    ids = {p["id"] for p in ordered}
    matrix = {str(p["id"]): {str(q["id"]): 0 for q in ordered} for p in ordered}
    category_totals = {str(p["id"]): dict(progression=0, useful=0, trap=0, filler=0) for p in ordered}
    location_totals = {str(p["id"]): 0 for p in ordered}
    recipient_totals = {str(p["id"]): 0 for p in ordered}
    crossworld = 0
    for finder, recipient, category in placements:
        if finder not in ids or recipient not in ids:
            # Archipelago supports grouped/link slots. Do not misattribute those items.
            continue
        if category not in ("progression", "useful", "trap", "filler"):
            category = "filler"
        f, r = str(finder), str(recipient)
        matrix[f][r] += 1
        location_totals[f] += 1
        recipient_totals[r] += 1
        category_totals[r][category] += 1
        if finder != recipient:
            crossworld += 1
    total = sum(location_totals.values())
    return {
        "source": "archipelago_generated_multiworld",
        "players": ordered,
        "total_placements": total,
        "crossworld_placements": crossworld,
        "crossworld_percent": round(crossworld * 100 / total, 1) if total else 0,
        "location_totals": location_totals,
        "recipient_totals": recipient_totals,
        "matrix": matrix,
        "categories": category_totals,
        "limitation": "Nur adressierte platzierte Items echter Spielerslots; Events, Startinventar und Item-Link-Gruppenslots werden nicht gezählt.",
    }


def game_overview(data):
    """Group by game, keeping recipient items distinct from world placements."""
    games = {}
    for player in data["players"]:
        game = games.setdefault(player["game"], {
            "name": player["game"], "players": [], "items": 0, "locations": 0,
        })
        pid = str(player["id"])
        game["players"].append({**player, "items": data["recipient_totals"][pid],
                                 "locations": data["location_totals"][pid]})
        game["items"] += data["recipient_totals"][pid]
        game["locations"] += data["location_totals"][pid]
    result = sorted(games.values(), key=lambda game: (-game["items"], game["name"].casefold()))
    for game in result:
        game["share"] = round(100 * game["items"] / data["total_placements"], 1) if data["total_placements"] else 0
    return result


def valid_item_details(data, distribution):
    """Only expose named placements that agree with the verified summary."""
    if (not isinstance(data, dict) or data.get("source") != distribution["source"]
            or not isinstance(data.get("placements"), list)):
        return False
    rows = data["placements"]
    if len(rows) != distribution["total_placements"]:
        return False
    ids = {p["id"] for p in distribution["players"]}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        if any(type(row.get(key)) is not int for key in ("finder", "recipient", "location_id", "item_id")):
            return False
        if row["finder"] not in ids or row["recipient"] not in ids:
            return False
        if any(not isinstance(row.get(key), str) for key in ("item", "location")):
            return False
        if row.get("category") not in ("progression", "useful", "trap", "filler"):
            return False
        location = (row["finder"], row["location_id"])
        if location in seen:
            return False
        seen.add(location)
    summary = aggregate_placements(distribution["players"],
                                   ((r["finder"], r["recipient"], r["category"]) for r in rows))
    return summary["matrix"] == distribution["matrix"] and summary["categories"] == distribution["categories"]


def progression_items(distribution, placements):
    """Group recipient progression items without putting their finders in the page."""
    players = {p["id"]: p for p in distribution["players"]}
    games = {p["game"]: {"name": p["game"], "items": [], "count": 0} for p in distribution["players"]}
    items = {}
    for index, row in enumerate(placements):
        if row["category"] != "progression":
            continue
        owner = players[row["recipient"]]
        key = (row["recipient"], row["item_id"], row["item"])
        game = games[owner["game"]]
        if key not in items:
            item = {"id": index, "name": row["item"], "recipient": owner, "count": 0}
            items[key] = item
            game["items"].append(item)
        items[key]["count"] += 1
        game["count"] += 1
    for game in games.values():
        game["items"].sort(key=lambda item: (item["name"].casefold(), item["recipient"]["name"].casefold(), item["id"]))
    return sorted(games.values(), key=lambda game: game["name"].casefold())


def progression_worlds(distribution, placements, index):
    """Reveal every concrete check for this recipient's item, grouped by world."""
    selected = placements[index]
    worlds = {}
    players = {p["id"]: p for p in distribution["players"]}
    for row in placements:
        if (row["category"] == "progression" and row["recipient"] == selected["recipient"]
                and row["item_id"] == selected["item_id"] and row["item"] == selected["item"]):
            world = worlds.setdefault(row["finder"], {**players[row["finder"]], "count": 0, "locations": []})
            world["count"] += 1
            world["locations"].append({"id": row["location_id"], "name": row["location"]})
    for world in worlds.values():
        world["locations"].sort(key=lambda location: (location["name"].casefold(), location["id"]))
    return sorted(worlds.values(), key=lambda world: (world["name"].casefold(), world["id"]))
