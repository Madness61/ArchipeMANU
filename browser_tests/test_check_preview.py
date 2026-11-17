"""Library reference count UX with an explicitly inert generator fixture."""
from playwright.sync_api import expect
from .test_players import register,upload_world


def test_library_check_preview_is_explicit_cached_and_mobile(actors,live_server,artifact_dir):
    page=actors.alice
    register(page,'CheckReader');upload_world(page)
    widget=page.locator('[data-check-preview]')
    expect(widget).to_contain_text('Standard-Checks noch nicht ermittelt')
    assert not (live_server.root/'check-preview-calls.txt').exists()
    page.get_by_role('button',name='Standard-Checks ermitteln',exact=True).click()
    expect(widget).to_contain_text('2 Item-Checks mit Spiel-Standard',timeout=15000)
    assert (live_server.root/'check-preview-calls.txt').exists()
    assert not live_server.calls()  # No lobby or actual round generation.
    page.reload()
    expect(widget).to_contain_text('2 Item-Checks mit Spiel-Standard')
    page.get_by_role('link',name='Spiel öffnen',exact=True).click()
    page.locator('[data-check-preview]').scroll_into_view_if_needed()
    expect(page.locator('[data-check-preview]')).to_contain_text('2 Item-Checks mit Spiel-Standard')
    for width in (1440,390):
        page.set_viewport_size(dict(width=width,height=1000))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(artifact_dir/f'standard-checks-{width}.png'),full_page=True)
