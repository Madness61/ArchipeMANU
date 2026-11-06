"""Deterministic aggregation of *real* placed Archipelago items.

Only call this with placements from a successfully generated MultiWorld.
No synthetic values, no importing/pickling uploaded seed archives.
"""
from collections import Counter


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
