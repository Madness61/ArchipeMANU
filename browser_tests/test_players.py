"""Real browser interactions; only AP execution is mocked in the test server."""
import io
import json
from contextlib import closing
import re
import sqlite3
import zipfile

from playwright.sync_api import expect
import yaml

from .fixtures import GAME, PASSWORD, world_bytes


def register(page,name,password=PASSWORD):
    page.goto("/register")
    page.get_by_label("Benutzername",exact=True).fill(name)
    expect(page.locator('input[name="invite_code"]')).to_have_count(0)
    expect(page.locator('input[name="password_confirm"]')).to_have_count(0)
    page.get_by_label("Passwort",exact=True).fill(password)
    page.get_by_role("button",name="Registrieren",exact=True).click()
    expect(page.get_by_role("heading",name=f"Hallo {name}")).to_be_visible()


def nav(page,name):
    return page.get_by_role("navigation",name="Hauptnavigation").get_by_role("link",name=name,exact=True)


def login(page,name,password=PASSWORD):
    page.goto("/login")
    page.get_by_label("Benutzername",exact=True).fill(name)
    page.get_by_label("Persönliches Passwort",exact=True).fill(password)
    page.get_by_role("button",name="Anmelden",exact=True).click()


def upload_world(page):
    page.goto("/games")
    page.get_by_role("link",name="+ Spiel hinzufügen",exact=True).click()
    page.get_by_label("Custom APWorld *",exact=True).set_input_files({
        "name":"browser_test_world.apworld","mimeType":"application/octet-stream","buffer":world_bytes()})
    page.get_by_label("Passende YAML-Vorlage (optional)",exact=True).set_input_files({
        "name":"browser-preset.yaml","mimeType":"text/yaml",
        "buffer":f"name: Fixture\ngame: {GAME}\n{GAME}:\n  goal: collect\n".encode()})
    page.get_by_role("button",name="Zur Spielebibliothek hinzufügen",exact=True).click()
    expect(page.get_by_role("heading",name=GAME,exact=True)).to_be_visible()
    # The actual JS must refresh queued/running extraction, not a test-side reload.
    expect(page.locator(".game-card").get_by_text("Für Lobby auswählbar",exact=True)).to_be_visible(timeout=15000)


def create_lobby(page,name):
    nav(page,"Lobbys").click()
    page.get_by_label("Neue Lobby",exact=True).fill(name)
    page.get_by_role("button",name="+ Lobby erstellen",exact=True).click()
    expect(page.get_by_role("heading",name=name,exact=True)).to_be_visible()
    expect(page.get_by_role("heading",name="Deine Spielauswahl",exact=True)).to_be_visible()
    expect(page.get_by_text("Alice · Spiel fehlt",exact=True)).to_be_visible()
    return page.url


def join_lobby(page,name):
    nav(page,"Lobbys").click()
    card = page.locator(".card").filter(has=page.get_by_role("heading",name=name,exact=True))
    expect(card.get_by_text("Offen",exact=True)).to_be_visible()
    card.get_by_role("button",name="Mitmachen →",exact=True).click()
    expect(page.get_by_role("heading",name=name,exact=True)).to_be_visible()
    expect(page.get_by_text("Bob · Spiel fehlt",exact=True)).to_be_visible()


def select_game(page,goal="finish",difficulty=3,death_link=False):
    page.get_by_role("combobox",name="Ich spiele:",exact=True).select_option("browser_test_world")
    page.get_by_role("button",name="YAML überarbeiten",exact=True).click()
    editor = page.locator("#selection-editor")
    editor.locator("details.group > summary").first.click()
    editor.get_by_role("combobox",name="Goal",exact=True).select_option(goal)
    editor.get_by_role("spinbutton",name="Difficulty",exact=True).fill(str(difficulty))
    editor.get_by_role("checkbox",name=re.compile("Death Link")).set_checked(death_link)
    editor.get_by_role("button",name="Vorschau aktualisieren",exact=True).click()
    preview = page.locator("#selection-preview pre").text_content()
    page.locator("#selection-editor").get_by_role("button",name="Auswahl übernehmen",exact=True).click()
    return preview


def slot_row(page,name):
    return page.locator("#participants tbody tr").filter(has=page.get_by_text(name,exact=True))


def edit_options(page,name,goal,difficulty,death_link=False):
    return select_game(page,goal,difficulty,death_link)


def mark_ready(page,name):
    slot_row(page,name).get_by_role("button",name="Bereit",exact=True).click()
    expect(slot_row(page,name).get_by_text("Bereit",exact=True)).to_be_visible()


def build_count(server):
    with sqlite3.connect((server.root/"hub.db").as_uri()+"?mode=ro",uri=True) as conn:
        count = conn.execute("SELECT COUNT(*) FROM seed_builds").fetchone()[0]
    conn.close()
    return count


def test_registration_login_logout_and_independent_identities(actors):
    alice,bob = actors.alice,actors.bob
    register(alice,"Alice",password="x")
    expect(alice.get_by_role("link",name="Admin",exact=True)).to_have_count(0)
    bob.goto("/profile")
    expect(bob.get_by_role("heading",name="Anmelden",exact=True)).to_be_visible()
    register(bob,"Bob")
    expect(alice.locator("header .me")).to_contain_text("Alice")
    expect(alice.locator("header .me")).not_to_contain_text("Bob")
    expect(bob.locator("header .me")).to_contain_text("Bob")
    alice.get_by_role("button",name="Abmelden",exact=True).click()
    login(alice,"Alice","incorrect password")
    expect(alice.locator(".flash.error")).to_contain_text("Benutzername oder Passwort ist falsch")
    login(alice,"Alice",password="x")
    expect(alice.get_by_role("heading",name="Hallo Alice")).to_be_visible()
    response = bob.goto("/admin")
    assert response.status == 403
    bob.goto("/profile")
    expect(bob.locator("header .me")).to_contain_text("Bob")


def test_shared_library_activation_two_player_lobby_and_seed_statistics(actors,live_server,artifact_dir):
    alice,bob,admin = actors.alice,actors.bob,actors.admin
    register(alice,"Alice")
    alice.screenshot(path=str(artifact_dir/"overview-desktop.png"),full_page=True)
    register(bob,"Bob")
    upload_world(alice)
    nav(bob,"Spielebibliothek").click()
    expect(bob.get_by_role("heading",name=GAME,exact=True)).to_be_visible()
    expect(bob.locator(".game-card").get_by_text("Für Lobby auswählbar",exact=True)).to_be_visible()

    # Uploads already activate automatically. Also exercise explicit host activation.
    login(admin,"TestAdmin")
    admin.locator("header").get_by_role("link",name="Admin",exact=True).click()
    admin.get_by_role("button",name="Deaktivieren",exact=True).click()
    admin.get_by_role("button",name="Aktivieren",exact=True).click()
    expect(admin.locator("#extract-status")).to_have_text("ok",timeout=15000)
    expect(admin.get_by_text("geladen",exact=True)).to_be_visible()

    lobby_url = create_lobby(alice,"Browser-Runde")
    bob.get_by_role("button",name="Abmelden",exact=True).click()
    login(bob,"Bob")
    join_lobby(bob,"Browser-Runde")
    preview_a = select_game(alice,"collect",7,True)
    preview_b = select_game(bob,"finish",2,False)
    alice.screenshot(path=str(artifact_dir/"lobby-desktop.png"),full_page=True)
    assert yaml.safe_load(preview_a)[GAME]["difficulty"] == 7
    assert yaml.safe_load(preview_b)[GAME]["difficulty"] == 2
    mark_ready(alice,"Alice")
    mark_ready(bob,"Bob")
    alice.reload()
    alice.get_by_role("button",name="Runde generieren",exact=True).click()
    build = alice.locator('[data-build-status="succeeded"]')
    expect(build).to_be_visible(timeout=15000)
    expect(alice.get_by_text("Geschlossen",exact=True)).to_be_visible()
    assert len(live_server.calls()) == 1
    assert build_count(live_server) == 1
    inputs = live_server.calls()[0]["yamls"]
    assert inputs == {"Alice.yaml":preview_a,"Bob.yaml":preview_b}
    with alice.expect_download() as download:
        build.get_by_role("link",name="Multiworld-ZIP herunterladen",exact=True).click()
    data = download.value.path().read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert yaml.safe_load(archive.read("configs/Alice.yaml"))[GAME] == yaml.safe_load(preview_a)[GAME]
    expect(build.get_by_role("heading", name="Raum-Link, Server & Port eintragen · Host", exact=True)).to_be_visible()
    build.get_by_label("Serveradresse",exact=True).fill("archipelago.gg")
    build.get_by_label("Port",exact=True).fill("38281")
    build.get_by_role("checkbox",name="Ich habe die Verbindung eingerichtet und geprüft.",exact=True).check()
    build.get_by_role("button",name="Verbindung speichern",exact=True).click()
    expect(alice.locator("#connection")).to_contain_text("archipelago.gg:38281")
    hosting = alice.locator("#connection .hosting-setup")
    expect(hosting).not_to_have_attribute("open", "")
    expect(hosting.get_by_label("Serveradresse", exact=True)).not_to_be_visible()
    hosting.locator(":scope > summary").click()
    expect(alice.locator("#connection").get_by_label("Serveradresse", exact=True)).to_have_value("archipelago.gg")
    expect(alice.locator("#connection").get_by_label("Port", exact=True)).to_have_value("38281")
    expect(alice.locator("#connection").get_by_role("button", name="Verbindung speichern", exact=True)).to_be_visible()
    hosting.locator(":scope > summary").click()
    expect(hosting.get_by_label("Serveradresse", exact=True)).not_to_be_visible()

    nav(alice,"Seed-Analyse").click()
    expect(alice.get_by_role("heading",name="Seed-Analysen",exact=True)).to_be_visible()
    alice.get_by_role("link",name="Statistik ansehen",exact=True).click()
    expect(alice.get_by_role("heading",name="Wie viele Items hat jedes Spiel?")).to_be_visible()
    expect(alice.locator("table").first).to_contain_text(GAME)
    expect(alice.locator(".matrix")).to_have_count(0)
    expect(alice.locator("#connection")).to_contain_text("archipelago.gg:38281")
    alice.screenshot(path=str(artifact_dir/"analysis-desktop.png"),full_page=True)
    progression = alice.locator(".progression-item").filter(has_text="für Alice")
    expect(progression).to_have_count(1)
    expect(progression).not_to_be_visible()
    expect(alice.locator(".progression-game[open]")).to_have_count(0)
    alice.locator(".progression-game > summary").first.click()
    expect(progression).to_contain_text("Key")
    expect(progression.locator(".progression-world")).to_be_empty()
    reveal_requests = []
    alice.on("request",lambda req: reveal_requests.append(req.url) if "/stats/progression/" in req.url else None)
    assert reveal_requests == []
    progression.get_by_text("Fundorte aufdecken",exact=True).click()
    expect(progression.locator(".progression-world")).to_contain_text(f"Chest — Bob · {GAME}")
    assert len(reveal_requests) == 1
    progression.get_by_text("Fundorte aufdecken",exact=True).click()
    expect(progression.locator(".progression-world")).not_to_be_visible()
    alice.get_by_role("link",name="Jetzt spielen / Verbindung",exact=True).click()
    expect(alice.locator("#check-analysis")).to_contain_text("4 platzierte Items insgesamt")
    expect(alice.get_by_text("Exakte Check-Zahlen",exact=False)).to_have_count(0)
    alice.get_by_role("link",name="Progression-Items und Seed-Analyse öffnen",exact=True).click()
    alice.get_by_role("link",name="Spoiler anzeigen & Details erkunden",exact=True).click()
    alice.get_by_text("Itemverteilung zwischen den Spielern",exact=True).click()
    expect(alice.locator(".matrix")).to_be_visible()
    alice.get_by_role("link",name="Spoiler wieder ausblenden",exact=True).click()
    expect(alice.locator(".matrix")).to_have_count(0)
    alice.get_by_role("link",name="Spoiler anzeigen & Details erkunden",exact=True).click()
    alice.get_by_role("link",name="Items für Alice",exact=True).click()
    expect(alice.get_by_role("heading",name="Items für Alice",exact=True)).to_be_visible()
    expect(alice.get_by_role("cell",name="Key",exact=True)).to_be_visible()
    bob.goto(lobby_url)
    bob.locator('[data-build-status="succeeded"]').get_by_role("link",name="Seed-Analyse",exact=True).click()
    expect(bob.get_by_role("heading",name=re.compile("Seed-Analyse #"))).to_be_visible()


def test_missing_readiness_and_invalid_yaml_do_not_start_generator(actors,live_server):
    alice,bob = actors.alice,actors.bob
    register(alice,"Alice")
    register(bob,"Bob")
    upload_world(alice)
    create_lobby(alice,"Blockierte Runde")
    join_lobby(bob,"Blockierte Runde")
    select_game(alice)
    select_game(bob)
    alice.reload()
    expect(alice.get_by_role("button",name="Runde generieren",exact=True)).to_be_disabled()
    expect(alice.locator("#host-controls")).to_contain_text("Noch nicht bereit")
    assert build_count(live_server) == 0
    assert live_server.calls() == []
    mark_ready(alice,"Alice")

    bob.get_by_role("button",name="YAML überarbeiten",exact=True).click()
    bob.locator("#selection-editor details.group > summary").first.click()
    bob.get_by_role("spinbutton",name="Difficulty",exact=True).fill("999")
    bob.get_by_role("button",name="Auswahl übernehmen",exact=True).click()
    expect(bob.get_by_text("Muss zwischen 1 und 10 liegen.",exact=False).first).to_be_visible()
    expect(bob.get_by_text("Keine gültige YAML:",exact=False)).to_be_visible()
    bob.locator("#selection-editor details.group > summary").first.click()
    bob.get_by_role("spinbutton",name="Difficulty",exact=True).fill("3")
    goal = bob.locator(".opt").filter(has=bob.locator("#f-goal"))
    goal.get_by_text("Gewichte oder komplexen YAML-Wert eingeben",exact=True).click()
    goal.get_by_role("checkbox",name="Diesen YAML-Wert verwenden (ersetzt das Feld oben)",exact=True).check()
    goal.get_by_role("textbox",name="YAML für Goal",exact=True).fill("finish: 0\ncollect: 0")
    bob.get_by_role("button",name="Auswahl übernehmen",exact=True).click()
    expect(bob.get_by_text("Alle Gewichte sind 0.",exact=False).first).to_be_visible()
    bob.get_by_role("link",name="Abbrechen",exact=True).click()
    expect(slot_row(bob,"Bob").get_by_text("Nicht bereit",exact=True)).to_be_visible()
    alice.reload()
    expect(alice.get_by_role("button",name="Runde generieren",exact=True)).to_be_disabled()
    expect(alice.locator("#host-controls")).to_contain_text("Bob: Noch nicht bereit")
    assert live_server.calls() == []
    assert build_count(live_server) == 0

    # Recovery through the UI must work without restarting or repairing data.
    edit_options(bob,"Bob","collect",4)
    mark_ready(bob,"Bob")
    alice.reload()
    alice.get_by_role("button",name="Runde generieren",exact=True).click()
    expect(alice.locator('[data-build-status="succeeded"]')).to_be_visible(timeout=15000)
    assert len(live_server.calls()) == 1


def test_mobile_library_filters_navigation_and_player_host_separation(actors,artifact_dir):
    alice,bob = actors.alice,actors.bob
    for page in (alice,bob):
        page.set_viewport_size({"width":390,"height":844})
        page.emulate_media(color_scheme="dark")  # Content stays light, as requested.
    register(alice,"Alice")
    register(bob,"Bob")
    navigation = alice.get_by_role("navigation",name="Hauptnavigation")
    expect(navigation.get_by_role("link")).to_have_count(4)
    expect(navigation.locator('[aria-current="page"]')).to_have_text("Übersicht")
    assert alice.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    alice.screenshot(path=str(artifact_dir/"overview-mobile.png"),full_page=True)
    upload_world(alice)
    expect(navigation.locator('[aria-current="page"]')).to_have_text("Spielebibliothek")
    alice.get_by_label("Spieltyp",exact=True).select_option("builtin")
    expect(alice.get_by_role("heading",name="Keine passenden Spiele gefunden")).to_be_visible()
    alice.get_by_label("Spieltyp",exact=True).select_option("custom")
    alice.get_by_label("Archipelago-Unterstützung",exact=True).select_option("loaded")
    alice.get_by_label("Spiel suchen",exact=True).fill("Browser")
    expect(alice.locator(".game-card:visible")).to_have_count(1)
    expect(alice.get_by_label("Spiel suchen",exact=True)).to_be_focused()
    alice.get_by_label("Genre",exact=True).select_option("Noch nicht zugeordnet")
    alice.get_by_label("Benötigte Einrichtung",exact=True).select_option("unknown")
    expect(alice.locator("#library-count")).to_have_text("1 von 1 Spielen")
    alice.get_by_label("Spiel suchen",exact=True).fill("keine-treffer")
    expect(alice.locator(".game-card:visible")).to_have_count(0)
    expect(alice.locator("#library-empty")).to_be_visible()
    alice.get_by_role("link",name="Zurücksetzen",exact=True).click()
    expect(alice.locator(".game-card:visible")).to_have_count(1)
    expect(alice.get_by_label("Genre",exact=True)).to_have_value("all")
    expect(alice.get_by_label("Spiel suchen",exact=True)).to_have_value("")
    assert alice.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    alice.screenshot(path=str(artifact_dir/"library-mobile.png"),full_page=True)
    alice.get_by_role("link",name="Spiel öffnen",exact=True).click()
    expect(alice.get_by_role("heading",name="So spielst du mit")).to_be_visible()
    expect(alice.get_by_role("heading",name="Vorlagen für deine Einstellungen")).to_be_visible()
    assert alice.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    create_lobby(alice,"Mobile Runde")
    join_lobby(bob,"Mobile Runde")
    expect(bob.locator("#host-controls")).to_have_count(0)
    expect(bob.get_by_role("button",name="Runde generieren",exact=True)).to_have_count(0)
    expect(alice.locator("#host-controls")).to_be_visible()
    expect(alice.get_by_role("button",name="Runde generieren",exact=True)).to_be_disabled()
    select_game(alice,"collect",5)
    select_game(bob,"finish",4)
    for page in (alice,bob):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    bob.screenshot(path=str(artifact_dir/"lobby-mobile.png"),full_page=True)
    nav(alice,"Übersicht").click()
    expect(alice.locator("#own-rounds")).to_contain_text("Mobile Runde")


def test_catalog_live_filters_and_game_setup(actors, live_server, artifact_dir):
    # Only inert schemas in this test's marked temporary root; never use live data.
    from hub.game_catalog import CATALOG
    index = {"games": {}, "failed": {}, "ap_version": "0.6.8"}
    for slug in CATALOG:
        name = {"smw": "Super Mario World", "aquaria": "Aquaria", "paint": "Paint"}.get(slug, slug)
        schema = {"game": name, "slug": slug, "version": "1.0", "custom": False,
                  "presets": {}, "items": [], "locations": [], "options": []}
        (live_server.root / "schemas" / (slug + ".json")).write_text(json.dumps(schema), encoding="utf-8")
        index["games"][slug] = {"game": name, "version": "1.0", "custom": False}
    (live_server.root / "schemas" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    page = actors.alice
    register(page, "Alice")
    page.goto("/games")
    expect(page.locator(".game-card:visible")).to_have_count(len(CATALOG))
    expect(page.get_by_text("Spielbereit", exact=True)).to_have_count(0)
    page.screenshot(path=str(artifact_dir / "catalog-desktop.png"))
    navigations = []
    page.on("request", lambda request: navigations.append(request.url) if request.is_navigation_request() else None)
    search = page.get_by_label("Spiel suchen", exact=True)
    search.fill("aquaria")
    expect(page.locator(".game-card:visible")).to_have_count(1)
    expect(search).to_be_focused()
    page.get_by_label("Genre", exact=True).select_option("Metroidvania")
    page.get_by_label("Benötigte Einrichtung", exact=True).select_option("rom")
    expect(page.locator("#library-empty")).to_be_visible()
    expect(page.locator("#library-count")).to_have_text(f"0 von {len(CATALOG)} Spielen")
    page.get_by_label("Benötigte Einrichtung", exact=True).select_option("mod")
    expect(page.locator(".game-card:visible h3")).to_have_text("Aquaria")
    assert not navigations, "Live filtering must not navigate or reload"
    filtered_url = page.url
    page.reload()
    expect(page.locator(".game-card:visible h3")).to_have_text("Aquaria")
    expect(page.get_by_label("Genre", exact=True)).to_have_value("Metroidvania")
    page.get_by_role("link", name="Zurücksetzen", exact=True).click()
    expect(page.locator(".game-card:visible")).to_have_count(len(CATALOG))
    search.fill("Super Mario World")
    expect(page.locator(".game-card:visible")).to_have_count(1)
    page.locator(".game-card:visible").get_by_role("link", name="Anleitung & Voraussetzungen").click()
    expect(page.locator("#game-guide")).to_contain_text("Super Mario World (USA).sfc")
    expect(page.locator("#game-guide")).to_contain_text("Generator-Rechner")
    expect(page.get_by_label("Voraussetzung für den Host", exact=True)).to_contain_text("vor der Generierung")
    expect(page.get_by_label("Voraussetzung für den Host", exact=True)).to_contain_text("separaten Server")
    expect(page.locator("#game-guide a[href*='tasvideos.org']")).to_have_count(1)
    page.screenshot(path=str(artifact_dir / "smw-setup-desktop.png"))
    page.set_viewport_size({"width": 390, "height": 1000})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.screenshot(path=str(artifact_dir / "smw-setup-mobile.png"))
    page.goto(filtered_url)
    expect(page.locator(".game-card:visible h3")).to_have_text("Aquaria")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.get_by_role("link", name="Spiel öffnen", exact=True).click()
    expect(page.locator("#game-guide")).to_contain_text("Eine Kopie des Aquaria-Spielordners")
    expect(page.locator("#game-guide a[href*='Aquaria_Randomizer']")).to_have_count(1)


def test_admin_deletes_accounts_rounds_and_seeds(actors, live_server):
    alice, admin = actors.alice, actors.admin
    register(alice, "Alice")
    upload_world(alice)
    lobby_url = create_lobby(alice, "Delete this round")
    select_game(alice)
    mark_ready(alice, "Alice")
    alice.get_by_role("button", name="Runde generieren", exact=True).click()
    expect(alice.locator('[data-build-status="succeeded"]')).to_be_visible()
    assert build_count(live_server) == 1
    login(admin, "TestAdmin")
    admin.goto("/admin")
    expect(admin.get_by_role("heading", name="Accounts verwalten", exact=True)).to_be_visible()
    # Dismiss confirmation: nothing is removed. Accept it on the next attempt.
    admin.evaluate("window.confirm = () => false")
    admin.get_by_role("button", name="Seed löschen", exact=True).click()
    assert build_count(live_server) == 1
    admin.evaluate("window.confirm = () => true")
    admin.get_by_role("button", name="Seed löschen", exact=True).click()
    expect(admin.locator(".flash")).to_contain_text("Seed #1")
    assert build_count(live_server) == 0
    assert not (live_server.root / "sessions/_seeds/1").exists()
    # The round survives the individual seed deletion and can generate again.
    alice.goto(lobby_url)
    expect(alice.get_by_role("heading", name="Delete this round", exact=True)).to_be_visible()
    alice.get_by_role("button", name="Runde generieren", exact=True).click()
    expect(alice.locator('[data-build-status="succeeded"]')).to_be_visible()
    admin.reload()
    admin.get_by_role("button", name="Runde löschen", exact=True).click()
    expect(admin.locator(".flash")).to_contain_text("Delete this round")
    assert build_count(live_server) == 0
    assert not (live_server.root / "sessions/_seeds/2").exists()
    response = alice.goto(lobby_url)
    assert response.status == 404
    admin.get_by_role("row").filter(has=admin.get_by_role("cell", name="Alice", exact=True)).get_by_role("button", name="Account löschen", exact=True).click()
    expect(admin.locator(".flash")).to_contain_text("Konto „Alice“ gelöscht")
    alice.goto("/profile")
    expect(alice.get_by_role("heading", name="Anmelden", exact=True)).to_be_visible()


def test_refresh_preserves_draft_and_active_lobby_navigation(actors, live_server, artifact_dir):
    alice, bob = actors.alice, actors.bob
    register(alice, "Alice")
    register(bob, "Bob")
    upload_world(alice)
    lobby_url = create_lobby(alice, "Live status round")
    join_lobby(bob, "Live status round")
    select_game(alice)
    alice.get_by_role("link", name="YAML / Einstellungen", exact=True).click()
    editor = alice.locator("#selection-editor")
    editor.locator("details.group > summary").first.click()
    editor.get_by_role("spinbutton", name="Difficulty", exact=True).fill("9")
    draft = editor.locator('input[name="_draft"]').input_value()
    select_game(bob)
    mark_ready(bob, "Bob")
    alice.get_by_role("link", name="Teilnehmer aktualisieren", exact=True).click()
    expect(alice.locator("#session-refresh-status")).to_have_text("Teilnehmer und generierte Runden wurden aktualisiert.")
    expect(editor.get_by_role("spinbutton", name="Difficulty", exact=True)).to_have_value("9")
    assert editor.locator('input[name="_draft"]').input_value() == draft
    expect(alice.locator("#participants-section")).to_contain_text("1 von 2 bereit")
    editor.get_by_role("button", name="Auswahl übernehmen", exact=True).click()
    mark_ready(alice, "Alice")
    alice.get_by_role("button", name="Runde generieren", exact=True).click()
    build = alice.locator('[data-build-status="succeeded"]')
    expect(build).to_be_visible()
    expect(build.get_by_role("heading", name="Raum-Link, Server & Port eintragen · Host", exact=True)).to_be_visible()
    expect(nav(alice, "Aktive Lobby")).to_have_count(0)
    build.get_by_label("Archipelago-Raum-Link (optional)", exact=True).fill("https://archipelago.gg/room/testroom")
    build.get_by_label("Serveradresse", exact=True).fill("archipelago.gg")
    build.get_by_label("Port", exact=True).fill("38281")
    build.get_by_role("checkbox", name="Ich habe die Verbindung eingerichtet und geprüft.", exact=True).check()
    alice.get_by_role("link", name="Runden aktualisieren", exact=True).click()
    expect(alice.locator("#session-refresh-status")).to_have_text("Teilnehmer und generierte Runden wurden aktualisiert.")
    expect(build.get_by_label("Serveradresse", exact=True)).to_have_value("archipelago.gg")
    expect(build.get_by_label("Port", exact=True)).to_have_value("38281")
    expect(build.get_by_role("checkbox", name="Ich habe die Verbindung eingerichtet und geprüft.", exact=True)).to_be_checked()
    alice.screenshot(path=str(artifact_dir / "hosting-visible-desktop.png"))
    build.get_by_role("button", name="Verbindung speichern", exact=True).click()
    expect(nav(alice, "Aktive Lobby")).to_be_visible()
    expect(nav(alice, "Aktive Lobby")).to_have_attribute("aria-current", "page")
    expect(alice.locator("#connection")).to_contain_text("archipelago.gg:38281")
    # Bob still has the old page. A manual refresh also updates his main navigation.
    bob.get_by_role("link", name="Runden aktualisieren", exact=True).click()
    expect(nav(bob, "Aktive Lobby")).to_be_visible()
    expect(bob.get_by_role("button", name="Verbindung speichern", exact=True)).to_have_count(0)
    nav(bob, "Aktive Lobby").click()
    expect(bob.get_by_role("heading", level=1)).to_contain_text("Live status round")
    expect(bob.locator("#connection")).to_contain_text("archipelago.gg:38281")
    expect(bob.locator("#connection a[href='https://archipelago.gg/room/testroom']")).to_be_visible()
    bob.set_viewport_size({"width": 390, "height": 844})
    assert bob.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    bob.screenshot(path=str(artifact_dir / "active-lobby-mobile.png"), full_page=True)
    alice.goto(lobby_url)
    expect(alice.locator("#generated-rounds").get_by_label("Port", exact=True)).to_have_value("38281")
    alice.set_viewport_size({"width": 390, "height": 844})
    assert alice.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    nav(alice, "Aktive Lobby").click()
    alice.get_by_role("button", name="Ich bin fertig", exact=True).click()
    expect(alice.locator("#completion")).to_contain_text("1 von 2 fertig")
    expect(alice.get_by_role("button", name="Ich spiele doch noch", exact=True)).to_be_visible()
    expect(nav(alice, "Aktive Lobby")).to_be_visible()
    bob.get_by_role("button", name="Spielstatus aktualisieren", exact=True).click()
    expect(bob.locator("#completion")).to_contain_text("1 von 2 fertig")
    bob.get_by_role("button", name="Ich bin fertig", exact=True).click()
    expect(bob.get_by_role("heading", level=1)).to_have_text("Abgeschlossene Runde · Live status round")
    expect(bob.locator("#completion")).to_contain_text("Alle Spieler haben bestätigt")
    expect(nav(bob, "Aktive Lobby")).to_have_count(0)
    bob.screenshot(path=str(artifact_dir / "completed-lobby-mobile.png"), full_page=True)
    alice.reload()
    expect(nav(alice, "Aktive Lobby")).to_have_count(0)
    expect(alice.get_by_role("button", name="Verbindung speichern", exact=True)).to_have_count(0)
    expect(alice.get_by_role("link", name="Multiworld-ZIP herunterladen", exact=True)).to_be_visible()
    alice.goto(lobby_url)
    expect(alice.locator("#session-overview")).to_contain_text("Abgeschlossen")
    expect(alice.get_by_role("button", name="Runde generieren", exact=True)).to_have_count(0)


def test_direct_defaults_template_explanation_and_single_value_reset(actors, live_server, artifact_dir):
    page = actors.alice
    register(page, "Alice")
    upload_world(page)
    create_lobby(page, "Simple selection")
    page.get_by_role("combobox", name="Ich spiele:", exact=True).select_option("browser_test_world")
    page.get_by_label("Grundeinstellungen", exact=True).select_option("default")
    expect(page.locator("#template-explanation")).to_contain_text("Spiel-Standard")
    page.get_by_role("button", name="Standardwerte übernehmen", exact=True).click()
    expect(page.locator("#selection-editor")).to_have_count(0)
    expect(slot_row(page, "Alice")).to_contain_text(GAME)
    expect(slot_row(page, "Alice")).to_contain_text("Nicht bereit")
    mark_ready(page, "Alice")
    page.get_by_role("link", name="YAML / Einstellungen", exact=True).click()
    editor = page.locator("#selection-editor")
    expect(editor.locator("details.group[open]")).to_have_count(0)
    editor.locator("details.group > summary").first.click()
    expect(editor.locator('input[name="_inherit"]')).to_have_count(0)
    editor.locator("#f-difficulty").fill("8")
    editor.locator("#f-goal").select_option("collect")
    editor.locator(".opt:has(#f-difficulty)").get_by_role("button", name="Diesen Wert zurücksetzen", exact=True).click()
    expect(editor.locator("#f-difficulty")).to_have_value("3")
    expect(editor.locator("#f-goal")).to_have_value("collect")
    # Reset changes only the draft; saved readiness survives until Apply.
    expect(slot_row(page, "Alice").get_by_text("Bereit", exact=True)).to_be_visible()
    page.screenshot(path=str(artifact_dir / "yaml-without-inheritance-checkboxes.png"))
    editor.get_by_role("button", name="Auswahl übernehmen", exact=True).click()
    expect(slot_row(page, "Alice")).to_contain_text("Nicht bereit")
    with closing(sqlite3.connect((live_server.root / "hub.db").as_uri() + "?mode=ro", uri=True)) as conn:
        overrides = json.loads(conn.execute("SELECT option_overrides FROM entries").fetchone()[0])
    assert overrides == {"goal": "collect"}
    ref = page.locator('#add-ref option[value^="c:"]').get_attribute("value")
    page.get_by_label("Grundeinstellungen", exact=True).select_option(ref)
    expect(page.locator("#template-explanation")).to_contain_text("Goal: Collect")
    expect(page.get_by_role("button", name="Vorlage übernehmen", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.locator("#select-game").scroll_into_view_if_needed()
    page.screenshot(path=str(artifact_dir / "simple-selection-mobile.png"))
    page.get_by_role("button", name="Vorlage übernehmen", exact=True).click()
    expect(page.locator("#selection-editor")).to_have_count(0)
    with closing(sqlite3.connect((live_server.root / "hub.db").as_uri() + "?mode=ro", uri=True)) as conn:
        saved_ref, overrides = conn.execute("SELECT template_ref,option_overrides FROM entries").fetchone()
    assert saved_ref == ref
    assert json.loads(overrides) == {}
