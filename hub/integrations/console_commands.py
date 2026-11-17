"""Supported, bounded text-client commands."""
COMMANDS = [
    ("/help", "Alle unterstützten Befehle anzeigen"),
    ("/connect", "Mit dem gespeicherten Server und deinem Slot verbinden"),
    ("/disconnect", "Textverbindung trennen; dein Spielclient bleibt verbunden"),
    ("/received", "Vom Server gemeldete Items für deinen Slot anzeigen"),
    ("/missing [Filter]", "Noch offene Checks deines Slots laut Server anzeigen"),
    ("/items [Filter]", "Itemnamen deines Spiels durchsuchen"),
    ("/locations [Filter]", "Check-Namen deines Spiels durchsuchen"),
    ("/hint [Item]", "Hinweis anfragen; der Server entscheidet über Kosten und Verfügbarkeit"),
    ("/hint_location [Check]", "Hinweis zu einem Check anfragen"),
    ("/status", "Serverstatus abfragen"), ("/players", "Mitspieler abfragen"),
    ("!remaining", "Verbleibende Items abfragen; abhängig von den Serverregeln"),
    ("!countdown [Sekunden]", "Countdown im Archipelago-Chat anfragen"),
]
SERVER_COMMANDS = {"!help", "!hint", "!hint_location", "!status", "!players", "!remaining", "!countdown"}
