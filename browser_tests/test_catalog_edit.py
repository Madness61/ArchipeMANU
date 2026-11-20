"""Catalog metadata and fluid desktop layout with real persistent Flask forms."""
import json
from playwright.sync_api import expect
from .fixtures import world_bytes, GAME
from .test_players import register
from .test_players import upload_world
from .test_preferences import set_preference


def test_game_metadata_upload_edit_filters_and_full_width(actors, live_server, artifact_dir):
    page = actors.alice
    register(page, "CatalogOwner")
    for width in (1440, 2560, 3840):
        page.set_viewport_size({"width": width, "height": 1080})
        bounds = page.locator("main.inner").bounding_box()
        assert abs(bounds["x"] + bounds["width"] - width) <= 2
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(artifact_dir / f"dashboard-full-width-{width}.png"), full_page=True)

    page.goto("/games/community/add")
    page.get_by_label("Kurzbeschreibung", exact=True).fill("Ein Abenteuer in eurer gemeinsamen Runde.")
    page.get_by_label("Genres", exact=True).fill("Adventure, Puzzle")
    expect(page.get_by_label("Tags", exact=True)).to_have_count(0)
    page.get_by_label("Custom APWorld *", exact=True).set_input_files({
        "name": "test.apworld", "mimeType": "application/octet-stream", "buffer": world_bytes()})
    page.get_by_role("button", name="Zur Spielebibliothek hinzufügen", exact=True).click()
    card = page.locator(".game-card").filter(has=page.get_by_role("heading", name=GAME, exact=True))
    expect(card).to_contain_text("Ein Abenteuer in eurer gemeinsamen Runde.")
    expect(card.locator(".catalog-tags")).to_have_count(0)
    expect(page.get_by_role("combobox", name="Tag", exact=True)).to_have_count(0)
    page.get_by_label("Spiel suchen", exact=True).fill("Abenteuer")
    page.get_by_role("combobox", name="Genre", exact=True).select_option("Puzzle")
    expect(page.locator("#library-count")).to_have_text("1 von 1 Spielen")
    page.reload()
    expect(card).to_be_visible()
    expect(card.get_by_role("link", name="Spiel bearbeiten", exact=True)).to_have_count(0)
    card.get_by_role("link", name="Spiel öffnen", exact=True).click()
    expect(page.get_by_role("heading", name=GAME, exact=True)).to_be_visible()
    expect(page.locator("#game-description")).to_contain_text("Ein Abenteuer in eurer gemeinsamen Runde.")
    assert page.locator("#game-overview").bounding_box()["y"] < page.locator("#game-guide").bounding_box()["y"]
    expect(page.locator("#game-tags")).to_have_count(0)
    expect(page.locator("#game-genres")).to_contain_text("Puzzle")
    page.get_by_label("Beschreibung bearbeiten", exact=True).click()
    page.get_by_label("Kurzbeschreibung", exact=True).fill("Unsere gespeicherte Spielbeschreibung.")
    for width in (1440, 768, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(artifact_dir / f"game-metadata-{width}.png"), full_page=True)
    page.locator("#game-description").get_by_role("button", name="Speichern", exact=True).click()
    expect(page.locator("#game-description")).to_contain_text("Unsere gespeicherte Spielbeschreibung.")
    page.get_by_label("Genres bearbeiten", exact=True).click()
    page.get_by_label("Genres", exact=True).fill("Metroidvania")
    page.locator("#game-genres").get_by_role("link", name="Abbrechen", exact=True).click()
    expect(page.locator("#game-genres")).to_contain_text("Puzzle")
    page.goto("/games?q=gespeicherte&tag=Dungeons")
    expect(card).to_be_visible()
    expect(page.locator("#library-count")).to_have_text("1 von 1 Spielen")
    page.set_viewport_size({"width": 2560, "height": 1440})
    page.screenshot(path=str(artifact_dir / "library-full-width-2560.png"), full_page=True)
    # A different member can see metadata but cannot change someone else's upload.
    register(actors.bob, "CatalogReader")
    actors.bob.goto("/games/browser_test_world")
    expect(actors.bob.get_by_label("Beschreibung bearbeiten", exact=True)).to_have_count(0)
    expect(actors.bob.get_by_role("link", name="Installationsanleitung bearbeiten", exact=True)).to_be_visible()
    response = actors.bob.goto("/games/browser_test_world/metadata/edit")
    assert response.status == 403


def test_unloaded_game_overview_contextual_edits_and_english_light_theme(actors, live_server, artifact_dir):
    page = actors.alice
    register(page, "PendingOwner")
    upload_world(page)
    # The test-only catalog retains the archive but has no loaded options.
    index_path = live_server.root / "schemas" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["games"].pop("browser_test_world")
    index_path.write_text(json.dumps(index), encoding="utf-8")
    page.goto("/games")
    card = page.locator(".game-card")
    expect(card.get_by_role("link", name="Spiel öffnen", exact=True)).to_be_visible()
    card.get_by_role("link", name="Spiel öffnen", exact=True).click()
    expect(page.get_by_role("heading", name=GAME, exact=True)).to_be_visible()
    expect(page.get_by_text("Checks und Vorlagen sind verfügbar", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Standard-Checks ermitteln", exact=True)).to_have_count(0)
    page.get_by_label("Genres bearbeiten", exact=True).click()
    page.get_by_label("Genres", exact=True).fill("Adventure, Puzzle")
    page.locator("#game-genres").get_by_role("button", name="Speichern", exact=True).click()
    expect(page.locator("#game-genres")).to_contain_text("Puzzle")
    page.get_by_role("link", name="Installationsanleitung bearbeiten", exact=True).click()
    page.get_by_label("Setup-Schritte (Text)", exact=True).fill("Mod installieren.")
    page.get_by_role("button", name="Guide speichern", exact=True).click()
    assert page.url.endswith("/games/browser_test_world#game-guide")
    expect(page.locator(".guide-author")).to_contain_text("PendingOwner")
    page.set_viewport_size(dict(width=1440, height=1000))
    set_preference(page, "language", "en")
    set_preference(page, "theme", "light")
    expect(page.get_by_label("Edit description", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Edit installation guide", exact=True)).to_be_visible()
    for width in (390, 768, 1440):
        page.set_viewport_size(dict(width=width, height=1000))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        guide_heading = page.locator("#group-guide h3").bounding_box()
        pencil = page.get_by_role("link", name="Edit installation guide", exact=True).bounding_box()
        assert pencil["x"] > guide_heading["x"] + guide_heading["width"]
        page.screenshot(path=str(artifact_dir / f"unloaded-overview-light-en-{width}.png"), full_page=True)
    page.goto("/games/browser_test_world/setup")
    expect(page.get_by_role("heading", name=GAME, exact=True)).to_be_visible()
    expect(page.locator("#game-genres")).to_contain_text("Puzzle")
