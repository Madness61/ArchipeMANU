"""Retired logic surface never starts an engine or reveals placements."""
from playwright.sync_api import expect
from .test_players import generated, register, upload_world, create_lobby, select_game, mark_ready

def test_retired_logic_has_explanation_and_no_worker_requests(actors, artifact_dir):
    page=actors.alice
    register(page,'Alice');upload_world(page)
    lobby=create_lobby(page,'Logikrunde');select_game(page);mark_ready(page,'Alice')
    page.reload();page.get_by_role('button',name='Seed generieren',exact=True).click()
    generated(page)
    response=page.goto(lobby.split('#')[0]+'/builds/1/live/logic')
    assert response.status==410
    expect(page.get_by_role('heading',name='Experimenteller Logik-Tracker deaktiviert')).to_be_visible()
    expect(page.locator('#logic-refresh')).to_have_count(0)
    expect(page.get_by_role('link',name='Zur Konsole',exact=True)).to_be_visible()
    for width in (1440,390):
        page.set_viewport_size(dict(width=width,height=900))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(artifact_dir/f'logic-disabled-{width}.png'),full_page=True)
