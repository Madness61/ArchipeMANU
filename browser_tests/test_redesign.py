"""Visual checks at phone/tablet/desktop widths on isolated, real Flask flows."""
import json
from copy import deepcopy
from playwright.sync_api import expect
import yaml

from .fixtures import GAME
from .test_players import register, login, nav, upload_world, create_lobby, join_lobby, select_game, mark_ready


def capture(page, directory, name):
    for width, height in ((1440, 1000), (768, 1024), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        toggle = page.locator("#menu-toggle")
        if toggle.is_visible() and toggle.get_attribute("aria-expanded") == "true":
            toggle.click()
        page.locator("#main-content").evaluate("node => {node.focus({preventScroll:true});node.blur();}")
        page.evaluate("window.scrollTo(0,0)")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"{name} overflows at {width}px"
        page.screenshot(path=str(directory / f"{name}-{width}.png"), full_page=True)


def test_dark_platform_navigation_options_and_responsive_pages(actors, live_server, artifact_dir):
    alice, bob, admin = actors.alice, actors.bob, actors.admin
    register(alice, "Alice"); register(bob, "Bob")
    expect(alice.locator("body")).to_have_css("background-color", "rgb(13, 19, 35)")
    capture(alice, artifact_dir, "dashboard-empty")
    alice.get_by_role("button", name="Menü öffnen", exact=True).click()
    expect(alice.locator("#main-content")).to_have_js_property("inert", True)
    alice.keyboard.press("Tab")
    expect(nav(alice, "Dashboard")).to_be_focused()
    alice.keyboard.press("Escape")
    expect(alice.get_by_role("button", name="Menü öffnen", exact=True)).to_be_focused()
    expect(alice.locator("#main-content")).to_have_js_property("inert", False)
    # Representative text/control contrast and reduced-motion behavior.
    alice.emulate_media(reduced_motion="reduce")
    primary = alice.get_by_role("link", name="Offene Lobbys ansehen", exact=True)
    for hover in (False, True):
        if hover: primary.hover()
        ratio = primary.evaluate("""node => {
          const style = getComputedStyle(node);
          const lum = color => {
            const rgb = color.match(/[\\d.]+/g).slice(0,3).map(v=>Number(v)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
            return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
          };
          const values=[lum(style.color),lum(style.backgroundColor)].sort((a,b)=>a-b);
          return (values[1]+.05)/(values[0]+.05);
        }""")
        assert ratio >= 4.5
    expect(primary).to_have_css("transition-duration", "0s")
    alice.emulate_media(reduced_motion="no-preference")

    upload_world(alice)
    # Catalog artwork uses local CSS/SVG. Extra inert schemas exercise real
    # catalog tags without downloading covers or running game integrations.
    index_file = live_server.root / "schemas" / "index.json"
    index = json.loads(index_file.read_text(encoding="utf-8"))
    original = json.loads((live_server.root / "schemas" / "browser_test_world.json").read_text(encoding="utf-8"))
    for slug, name in (("smw", "Super Mario World"), ("hk", "Hollow Knight"), ("ror2", "Risk of Rain 2"),
                       ("aquaria", "Aquaria"), ("pseudoregalia", "Pseudoregalia"), ("RE4R", "Resident Evil 4 Remake")):
        schema = {**deepcopy(original), "slug": slug, "game": name, "custom": False}
        (live_server.root / "schemas" / (slug + ".json")).write_text(json.dumps(schema), encoding="utf-8")
        index["games"][slug] = {"game": name, "version": "1.0.0", "custom": False}
    index_file.write_text(json.dumps(index), encoding="utf-8")
    alice.goto("/games")
    expect(alice.locator(".game-card")).to_have_count(7)
    expect(alice.get_by_role("img", name="Grafisches Titelbild für Super Mario World", exact=True)).to_be_visible()
    capture(alice, artifact_dir, "library")
    alice.locator(".game-card").filter(has=alice.get_by_role("heading", name=GAME, exact=True)).get_by_role("link", name="Spiel öffnen", exact=True).click()
    capture(alice, artifact_dir, "game-detail")
    alice.get_by_role("link", name="+ Neue Vorlage", exact=True).click()
    capture(alice, artifact_dir, "template-editor")
    alice.goto("/import")
    capture(alice, artifact_dir, "yaml-import")

    lobby = create_lobby(alice, "Zwischen Welten")
    join_lobby(bob, "Zwischen Welten")
    expect(alice.locator("#session-overview")).to_contain_text("Host: Alice")
    alice.get_by_role("link", name="Teilnehmer aktualisieren", exact=True).click()
    expect(alice.locator("#participants tbody tr")).to_have_count(2)
    capture(alice, artifact_dir, "lobby-waiting")
    nav(alice, "Dashboard").click()
    expect(alice.locator("#featured-action")).to_have_text("Spiel auswählen")
    capture(alice, artifact_dir, "dashboard-preparation")
    alice.locator("#featured-action").click()
    alice.get_by_text("Spielkatalog öffnen", exact=True).click()
    alice.get_by_role("searchbox", name="Spiel im Katalog suchen", exact=True).fill("Browser")
    expect(alice.locator("[data-choose-game]:visible")).to_have_count(1)
    alice.get_by_role("button", name=GAME, exact=True).click()
    expect(alice.get_by_role("combobox", name="Ich spiele:", exact=True)).to_have_value("browser_test_world")
    alice.get_by_role("button", name="Einstellungen anpassen", exact=True).click()
    editor = alice.locator("#selection-editor")
    expect(editor.locator("details.group[open]")).to_have_count(0)
    editor.get_by_role("searchbox", name="Optionen suchen", exact=True).fill("Difficulty")
    expect(editor.locator(".opt:visible")).to_have_count(1)
    editor.get_by_role("spinbutton", name="Difficulty", exact=True).fill("7")
    editor.get_by_role("spinbutton", name="Difficulty", exact=True).press("Tab")
    expect(editor.locator(".edit-flag:visible")).to_have_count(1)
    editor.get_by_text("Angepasste Werte", exact=False).click()
    expect(editor.locator("[data-option-changes]")).to_contain_text("Difficulty")
    capture(alice, artifact_dir, "lobby-options")
    editor.get_by_role("button", name="Auswahl übernehmen", exact=True).click()
    nav(alice, "Dashboard").click()
    expect(alice.locator("#featured-action")).to_have_text("Bereit melden")
    alice.locator("#featured-action").click()
    mark_ready(alice, "Alice")
    select_game(bob, "collect", 4)
    mark_ready(bob, "Bob")
    alice.goto(lobby)
    expect(alice.locator("#participants-section")).to_contain_text("2 von 2 bereit")
    expect(alice.get_by_role("button", name="Seed generieren", exact=True)).to_be_enabled()
    capture(alice, artifact_dir, "lobby-ready")
    alice.get_by_role("button", name="Seed generieren", exact=True).click()
    build = alice.locator('[data-build-status="succeeded"]')
    expect(build).to_be_visible(timeout=15000)
    generated = yaml.safe_load(live_server.calls()[0]["yamls"]["Alice.yaml"])
    assert generated[GAME]["difficulty"] == 7
    assert generated[GAME]["goal"] == "finish"  # hidden by the option search, still submitted
    assert generated[GAME]["death_link"] is False
    build.get_by_role("link", name="Jetzt spielen", exact=True).click()
    play_url = alice.url
    alice.get_by_label("Archipelago-Raum für Live-Statistiken", exact=True).fill("https://archipelago.gg/room/AAECAwQFBgcICQoLDA0ODw")
    alice.get_by_role("button", name="Raum verbinden", exact=True).click()
    expect(alice.locator("#kpi-checks")).to_have_text("2", timeout=15000)
    expect(alice.locator("#live-overview-players .overview-player")).to_have_count(2)
    capture(alice, artifact_dir, "live-overview")
    alice.set_viewport_size({"width": 1440, "height": 1000})
    alice.get_by_role("button", name="Präsentationsmodus", exact=True).click()
    alice.screenshot(path=str(artifact_dir / "live-presentation-1440.png"), full_page=False)
    alice.get_by_role("button", name="Präsentation beenden", exact=True).click()
    alice.goto("/")
    expect(alice.locator("#featured-action")).to_have_text("Live-Dashboard öffnen")
    capture(alice, artifact_dir, "dashboard-active")
    alice.goto(play_url)
    expect(alice.locator("#server-host")).to_have_text("archipelago.gg")
    expect(alice.locator("#server-port")).to_have_text("38281")
    expect(alice.locator("#slot-1")).to_have_text("Alice")
    expect(alice.get_by_role("button", name="Server kopieren", exact=True)).to_be_visible()
    capture(alice, artifact_dir, "play")
    alice.get_by_text("Technische Informationen & Check-Analyse", exact=True).click()
    alice.get_by_role("link", name="Progression-Items und Seed-Analyse öffnen", exact=True).click()
    expect(alice.locator(".progression-game[open]")).to_have_count(0)
    expect(alice.locator(".matrix")).to_have_count(0)
    capture(alice, artifact_dir, "seed-analysis")
    alice.goto("/profile")
    capture(alice, artifact_dir, "profile")
    login(admin, "TestAdmin")
    admin.goto("/admin")
    capture(admin, artifact_dir, "admin")
    alice.get_by_role("button", name="Menü öffnen", exact=True).click()
    alice.get_by_role("button", name="Abmelden", exact=True).click()
    expect(alice.get_by_role("heading", name="Anmelden", exact=True)).to_be_visible()
    capture(alice, artifact_dir, "login")
