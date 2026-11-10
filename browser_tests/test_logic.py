"""Logic tracker presentation with controlled API responses; no game logic mock in production."""
import json
from playwright.sync_api import expect
from .test_players import register, upload_world, create_lobby, select_game, mark_ready


def test_logic_ui_filters_spoilers_and_mobile(actors, artifact_dir):
    page=actors.alice
    register(page,'Alice');upload_world(page)
    lobby=create_lobby(page,'Logikrunde');select_game(page);mark_ready(page,'Alice')
    page.reload();page.get_by_role('button',name='Seed generieren',exact=True).click()
    build=page.locator('[data-build-status="succeeded"]')
    expect(build).to_be_visible(timeout=15000)
    build.get_by_role('link',name='Jetzt spielen',exact=True).click()
    logic_url=page.url+'/live/logic'  # play_page is the build root
    logic_url=logic_url.replace('/play/live/logic','/live/logic')
    # The real route still enforces account ownership; only computed data is a fixture.
    state=dict(state='ready',engine='Universal Tracker (test fixture)',slot='Alice',observed_at=1770000000,
        reachable=1,remaining=2,go_mode=True,deferred_entrances=0,inventory=[dict(name='Key',count=1)],
        locations=[dict(id=1,name='Start Chest',region='Town',reachable=True,checked=False),
                   dict(id=2,name='Locked Cave',region='Cave',reachable=False,checked=False)])
    reveals=[]
    refreshes=[]
    page.route('**/live/logic/data*',lambda route:route.fulfill(json=state if refreshes else dict(state='idle',error='Noch keine Berechnung')))
    def refresh(route):
        refreshes.append(True)
        route.fulfill(json=state)
    page.route('**/live/logic/refresh',refresh)
    def reveal(route):
        reveals.append(True)
        route.fulfill(json=dict(placements=[dict(id=1,item='Hidden Sword',recipient='Alice')]))
    page.route('**/live/logic/placements',reveal)
    page.goto(logic_url)
    expect(page.get_by_role('heading',name='Logik-Tracker',exact=True)).to_be_visible()
    expect(page.locator('#logic-go')).to_have_text('Ja')
    assert len(refreshes)==1  # Automatic calculation after the initial server snapshot.
    expect(page.locator('.logic-location')).to_have_count(1)
    expect(page.locator('#logic-locations')).not_to_contain_text('Hidden Sword')
    assert not reveals
    page.get_by_label('Logikstatus',exact=True).select_option('blocked')
    expect(page.locator('#logic-locations')).to_contain_text('Locked Cave')
    page.get_by_label('Logikstatus',exact=True).select_option('reachable')
    page.get_by_text('Iteminhalte aufdecken · Spoiler',exact=True).click()
    assert not reveals
    page.get_by_role('button',name='Iteminhalte ausdrücklich aufdecken',exact=True).click()
    expect(page.locator('#logic-locations')).to_contain_text('Hidden Sword')
    for width in (1440,768,390):
        page.set_viewport_size(dict(width=width,height=1000))
        page.locator('#main-content').evaluate('node => {node.focus({preventScroll:true});node.blur();}')
        page.evaluate('window.scrollTo(0,0)')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(artifact_dir/f'logic-tracker-{width}.png'),full_page=True)
    state.update(state='unsupported',error='Nicht passende APWorld-Version')
    page.get_by_role('button',name='Logik aktualisieren',exact=True).click()
    expect(page.locator('#logic-go')).to_have_text('Unbekannt')
    expect(page.locator('#logic-locations')).not_to_contain_text('Hidden Sword')
