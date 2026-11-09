"""Catalog metadata and fluid desktop layout with real persistent Flask forms."""
from playwright.sync_api import expect
from .fixtures import world_bytes, GAME
from .test_players import register


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
    page.get_by_label("Tags", exact=True).fill("Erkundung, 2D, erkundung")
    page.get_by_label("Custom APWorld *", exact=True).set_input_files({
        "name": "test.apworld", "mimeType": "application/octet-stream", "buffer": world_bytes()})
    page.get_by_role("button", name="Zur Spielebibliothek hinzufügen", exact=True).click()
    card = page.locator(".game-card").filter(has=page.get_by_role("heading", name=GAME, exact=True))
    expect(card).to_contain_text("Ein Abenteuer in eurer gemeinsamen Runde.")
    expect(card.locator(".catalog-tags .chip")).to_have_count(2)
    page.get_by_role("combobox", name="Tag", exact=True).select_option("Erkundung")
    page.get_by_role("combobox", name="Genre", exact=True).select_option("Puzzle")
    expect(page.locator("#library-count")).to_have_text("1 von 1 Spielen")
    page.reload()
    expect(card).to_be_visible()
    card.get_by_role("link", name="Spiel bearbeiten", exact=True).click()
    expect(page.get_by_label("Tags", exact=True)).to_have_value("Erkundung, 2D")
    page.get_by_label("Tags", exact=True).fill("Dungeons, Rätselrunde")
    page.get_by_label("Kurzbeschreibung", exact=True).fill("Unsere gespeicherte Spielbeschreibung.")
    for width in (1440, 768, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(artifact_dir / f"game-metadata-{width}.png"), full_page=True)
    page.get_by_role("button", name="Spielangaben speichern", exact=True).click()
    expect(page.locator("#game-guide")).to_contain_text("Unsere gespeicherte Spielbeschreibung.")
    page.goto("/games?q=Rätselrunde&tag=Dungeons")
    expect(card).to_be_visible()
    expect(page.locator("#library-count")).to_have_text("1 von 1 Spielen")
    page.set_viewport_size({"width": 2560, "height": 1440})
    page.screenshot(path=str(artifact_dir / "library-full-width-2560.png"), full_page=True)
    # A different member can see metadata but cannot change someone else's upload.
    register(actors.bob, "CatalogReader")
    response = actors.bob.goto("/games/browser_test_world/metadata/edit")
    assert response.status == 403
