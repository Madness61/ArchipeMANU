"""Two real browsers and the real bridge against an inert localhost AP protocol server."""
import json
import re

from playwright.sync_api import expect

from .fake_ap import FakeAP
from .fixtures import GAME
from .test_players import area, generated, register, upload_world, create_lobby, join_lobby, select_game, mark_ready


def configure_room(page, password=''):
    settings=page.locator('#console-room-settings')
    if settings.get_attribute('open') is None:
        settings.locator('summary').click()
    page.get_by_label('Raumpasswort (optional)',exact=True).fill(password)
    page.get_by_label('Verbindungsart',exact=True).select_option('ws')
    page.get_by_role('button',name='Raumverbindung aktualisieren',exact=True).click()
    expect(page.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS',timeout=20000)


def test_shared_reader_inline_finder_and_spectator(actors,artifact_dir):
    from .test_players import login
    from .test_redesign import capture
    a,b,viewer=actors.alice,actors.bob,actors.admin
    with FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST') as server:
        server.announce_joins = True
        register(a,'Alice');register(b,'Bob');upload_world(a)
        create_lobby(a,'Ein gemeinsamer Verlauf');join_lobby(b,'Ein gemeinsamer Verlauf')
        select_game(a);select_game(b);mark_ready(a,'Alice');mark_ready(b,'Bob')
        a.reload();a.get_by_role('button',name='Seed generieren',exact=True).click()
        host=generated(a)
        host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
        host.get_by_label('Port',exact=True).fill(str(server.port))
        host.get_by_role('button',name='Verbindung speichern',exact=True).click()
        expect(a.locator('#console-state')).to_contain_text('Mit Archipelago verbunden',timeout=20000)
        url=a.url;base=a.locator('#ap-console').get_attribute('data-base')
        b.goto(url);login(viewer,'TestAdmin');viewer.goto(url)
        for page in (a,b,viewer):
            expect(page.locator('#console-log')).to_contain_text('Progression Key')
            expect(page.locator('#console-log').get_by_text('Itemaufzeichnung gestartet', exact=False)).to_have_count(1)
            expect(page.locator('#console-log')).not_to_contain_text('Alice tracking has joined.')
            expect(page.locator('#console-connect')).to_have_count(0)
        assert len(server.clients)==1
        server.send(server.clients[0], [dict(cmd='PrintJSON', type='Join', team=0, slot=1, tags=['AP'],
                                             data=[dict(text='Alice playing has joined.')])])
        for page in (a,b,viewer):
            expect(page.locator('#console-log')).to_contain_text('Alice playing has joined.')
        expect(viewer.locator('#console-command')).to_have_count(0)
        blocked=viewer.evaluate("""async base=>{const response=await fetch(base+'/command',{method:'POST',headers:{'X-CSRF-Token':document.getElementById('ap-console').dataset.csrf},body:new URLSearchParams({text:'/hint Key',slot:'Alice',automatic:'1'})});return response.status;}""",base)
        assert blocked==403
        for page in (a,b):
            page.get_by_label('Nachricht oder Befehl',exact=True).fill('/hint Key')
            page.get_by_role('button',name='Senden',exact=True).click()
        expect(a.locator('#console-log')).to_contain_text('Privater Hinweis für Alice')
        expect(b.locator('#console-log')).to_contain_text('Privater Hinweis für Bob')
        expect(b.locator('#console-log')).not_to_contain_text('Privater Hinweis für Alice')
        expect(viewer.locator('#console-log')).not_to_contain_text('Privater Hinweis')
        assert sorted(server.commands)==[('Alice','!hint Key'),('Bob','!hint Key')]
        assert len(server.clients)==3
        a.get_by_label('Nachricht oder Befehl',exact=True).fill('Hallo Bob, gemeinsam lesen!')
        a.get_by_role('button',name='Senden',exact=True).click()
        for page in (a,b,viewer):
            expect(page.locator('#console-log')).to_contain_text('Hallo Bob, gemeinsam lesen!')
            expect(page.locator('.console-chat')).to_have_count(1)
        b.locator('#console-log .console-player-name').first.click()
        expect(b.locator('#round-player-name')).to_have_text('Bob')
        expect(b.locator('[data-round-view="players"]')).to_have_attribute('aria-current','page')
        finder=a.locator('#live-item-finder')
        finder.get_by_label('Item, Spieler oder Fundort',exact=True).fill('Key')
        finder.get_by_role('button',name='Suchen',exact=True).click()
        expect(finder.locator('#live-item-results')).not_to_contain_text('Chest')
        finder.get_by_role('button',name='Fundort-Spoiler bewusst freigeben',exact=True).click()
        expect(finder.locator('.live-item-result')).to_have_count(2)
        expect(finder.locator('#live-item-count')).to_have_text('2 Treffer')
        expect(finder.locator('#live-item-next')).to_be_hidden()
        expect(finder.locator('#live-item-results')).to_contain_text('Bob')
        expect(finder.locator('#live-item-results')).to_contain_text('Chest')
        server.send(server.clients[0], [dict(cmd='PrintJSON', type='ItemSend', receiving=1, item=[1, 20, 2, 1])])
        expect(finder.locator('.live-item-result').filter(has_text='Empfänger: Alice')).to_contain_text('Gefunden')
        expect(a.locator('#progression-panel')).not_to_be_visible()
        expect(a.locator('#console-log')).to_contain_text('Hallo Bob, gemeinsam lesen!')
        capture(a,artifact_dir,'shared-console-inline-search')
        finder.get_by_role('button',name='Spoiler wieder sperren',exact=True).click()
        expect(finder.locator('.live-item-result')).to_have_count(0)
        assert all(packet['cmd'] not in ('LocationChecks','LocationScouts','StatusUpdate') for packet in server.packets)


def test_console_items_commands_private_hints_and_mobile(actors, artifact_dir):
    alice,bob = actors.alice,actors.bob
    with FakeAP(game=GAME,names=("Alice","Bob"),seed="BROWSER_TEST",password="Test room") as server:
        register(alice,"Alice"); register(bob,"Bob")
        upload_world(alice)
        lobby = create_lobby(alice,"Unsere Konsolenrunde")
        join_lobby(bob,"Unsere Konsolenrunde")
        select_game(alice); select_game(bob)
        mark_ready(alice,"Alice"); mark_ready(bob,"Bob")
        alice.reload()
        alice.get_by_role("button",name="Seed generieren",exact=True).click()
        build = generated(alice)
        build.get_by_label("Serveradresse",exact=True).fill("127.0.0.1")
        build.get_by_label("Port",exact=True).fill(str(server.port))
        build.get_by_role("button",name="Verbindung speichern",exact=True).click()
        expect(alice.get_by_role("heading",level=1)).to_have_text("Unsere Konsolenrunde")
        expect(alice.locator('#ap-console')).to_be_visible()
        expect(alice.locator('[data-round-view="play"]')).to_have_text('Live')
        expect(alice.locator("#console-error")).to_contain_text("Raumpasswort",timeout=15000)
        configure_room(alice,'Test room')
        expect(alice.locator("#console-state")).to_have_text("Mit Archipelago verbunden · WS",timeout=15000)
        expect(alice.locator("#console-error")).to_be_hidden()
        expect(alice.locator("#console-log")).to_contain_text("Bob → Alice: Progression Key",timeout=15000)
        expect(alice.locator("#console-log")).to_contain_text("Old Fortress - Chest")
        console_url = alice.url
        bob.goto(console_url)
        expect(bob.locator('#console-connect')).to_have_count(0)
        expect(bob.locator("#console-log")).to_contain_text("Bob → Alice: Progression Key")
        alice.get_by_role('button',name='Befehl einfügen',exact=True).click()
        alice.locator('[data-insert-command="/hint "]').click()
        expect(alice.get_by_label('Nachricht oder Befehl',exact=True)).to_have_value('/hint ')
        assert not any(p['cmd']=='Say' for p in server.packets)
        alice.get_by_label("Nachricht oder Befehl",exact=True).fill("/hint Progression Key")
        alice.get_by_role("button",name="Senden",exact=True).click()
        expect(alice.locator("#console-log")).to_contain_text("Privater Hinweis für Alice")
        expect(alice.locator("#console-log")).to_contain_text("<script>never_execute()</script>")
        assert not alice.evaluate("typeof never_execute !== 'undefined'")
        expect(bob.locator("#console-log")).not_to_contain_text("Privater Hinweis für Alice")
        alice.get_by_label("Nachricht oder Befehl",exact=True).fill("/rec")
        expect(alice.locator('#console-command-menu')).to_be_visible()
        alice.keyboard.press('ArrowDown');alice.keyboard.press('Enter')
        expect(alice.get_by_label('Nachricht oder Befehl',exact=True)).to_have_value('/received')
        assert sum(p['cmd']=='Say' for p in server.packets)==1
        alice.get_by_role("button",name="Senden",exact=True).click()
        expect(alice.locator("#console-log")).to_contain_text("Progression Key ← Bob")
        alice.get_by_label("Nachricht oder Befehl",exact=True).fill("Hallo zusammen!")
        alice.get_by_role("button",name="Senden",exact=True).click()
        expect(alice.locator("#console-log")).to_contain_text("Alice: Hallo zusammen!")
        alice.get_by_label('Nachricht oder Befehl',exact=True).fill('Entwurf bleibt erhalten')
        server.accept_connections = False
        server.interrupt()
        expect(alice.locator('#console-state')).to_have_text('Verbindung wird wiederhergestellt')
        expect(alice.locator('#console-error')).to_be_hidden()
        expect(alice.locator('#console-log').get_by_text('Itemaufzeichnung unterbrochen', exact=False)).to_have_count(1)
        expect(alice.locator('#console-log')).not_to_contain_text('Textverbindung unterbrochen. Automatische Wiederverbindung')
        alice.get_by_text('Verbindungsdiagnose', exact=True).click()
        expect(alice.locator('#console-diagnostics')).to_contain_text('Letzter Verbindungsfehler')
        expect(alice.locator('#console-diagnostics')).to_contain_text('AP-Slot des Hintergrundlesers')
        for width, height, mode in ((390, 844, 'mobile'), (1365, 950, 'desktop')):
            alice.set_viewport_size(dict(width=width, height=height))
            alice.locator('#main-content').evaluate('n=>{n.focus({preventScroll:true});n.blur()}')
            alice.evaluate('window.scrollTo(0,0)')
            assert alice.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            alice.screenshot(path=str(artifact_dir/f'console-reconnecting-{mode}.png'), full_page=True)
        server.accept_connections = True
        expect(alice.locator('#console-log').get_by_text('Itemaufzeichnung fortgesetzt', exact=False)).to_have_count(1, timeout=20000)
        expect(alice.get_by_label('Nachricht oder Befehl',exact=True)).to_have_value('Entwurf bleibt erhalten')
        assert sum(p.get('text')=='Hallo zusammen!' for p in server.packets)==1
        alice.locator('#main-content').evaluate('n=>{n.focus({preventScroll:true});n.blur()}');alice.evaluate('window.scrollTo(0,0)')
        alice.screenshot(path=str(artifact_dir/"console-desktop.png"),full_page=True)
        alice.get_by_label("Nachrichtenart",exact=True).select_option("items")
        expect(alice.locator(".console-items")).to_have_count(1)
        expect(alice.locator("#console-log")).not_to_contain_text("Privater Hinweis")
        alice.set_viewport_size({"width":390,"height":844})
        assert alice.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        alice.locator('#main-content').evaluate('n=>{n.focus({preventScroll:true});n.blur()}');alice.evaluate('window.scrollTo(0,0)')
        alice.screenshot(path=str(artifact_dir/"console-mobile.png"),full_page=True)
        # Legacy detail route reuses the exact same console, history and commands.
        alice.goto(console_url.replace('/play','/console'))
        expect(alice.get_by_role('heading',level=1)).to_have_text('Konsole · Unsere Konsolenrunde')
        expect(alice.locator('#ap-console')).to_have_count(1)
        expect(alice.locator('#console-log')).to_contain_text('Progression Key')
        expect(bob.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS')
        expect(bob.locator('#console-log')).to_contain_text('Alice: Hallo zusammen!')
        assert any(p.get("cmd")=="Say" and p.get("text")=="!hint Progression Key" for p in server.packets)
        assert all(p["cmd"] not in ("LocationChecks","StatusUpdate","LocationScouts") for p in server.packets)


def test_official_room_port_rotation_updates_console_and_copy_address_without_reload(actors,live_server,artifact_dir):
    alice,bob=actors.alice,actors.bob
    with FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST',password='Test room') as first, FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST',password='Test room') as second:
        stage=live_server.root/'live-stage.json'
        def publish(port,offset=0):
            pending=live_server.root/'live-stage-pending.json'
            pending.write_text(json.dumps(dict(port=port,offset=offset,local_ports=[first.port,second.port])),encoding='utf-8')
            pending.replace(stage)
        publish(first.port)
        register(alice,'Alice');register(bob,'Bob');upload_world(alice)
        create_lobby(alice,'Portwechsel');join_lobby(bob,'Portwechsel')
        select_game(alice);select_game(bob);mark_ready(alice,'Alice');mark_ready(bob,'Bob')
        alice.reload();alice.get_by_role('button',name='Seed generieren',exact=True).click()
        build=generated(alice)
        build.get_by_label('Archipelago-Raum-Link (optional)',exact=True).fill('https://archipelago.gg/room/AAECAwQFBgcICQoLDA0ODw')
        build.get_by_label('Serveradresse',exact=True).fill('archipelago.gg')
        build.get_by_label('Port',exact=True).fill(str(first.port))
        expect(build.get_by_label('Port manuell festlegen (keine automatische Aktualisierung)',exact=True)).not_to_be_checked()
        build.get_by_role('button',name='Verbindung speichern',exact=True).click()
        configure_room(alice,'Test room')
        expect(alice.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS')
        expect(alice.locator('.console-items')).to_have_count(1)
        alice.get_by_label('Nachricht oder Befehl',exact=True).fill('Entwurf bleibt beim Portwechsel')
        publish(second.port,61)
        expect(alice.locator('#console-log')).to_contain_text('neuen Port',timeout=20000)
        expect(alice.locator('#console-log').get_by_text('Itemaufzeichnung unterbrochen', exact=False)).to_have_count(1)
        expect(alice.locator('#console-log').get_by_text('Itemaufzeichnung fortgesetzt', exact=False)).to_have_count(1, timeout=20000)
        expect(alice.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS')
        expect(alice.locator('#console-server-address')).to_have_text(f'archipelago.gg:{second.port}')
        expect(alice.locator('#console-auto-port')).to_be_visible()
        expect(alice.locator('#host-address')).to_have_text(f'archipelago.gg:{second.port}')
        expect(alice.locator('.console-items')).to_have_count(1)
        expect(alice.get_by_label('Nachricht oder Befehl',exact=True)).to_have_value('Entwurf bleibt beim Portwechsel')
        login, = [p for p in second.packets if p['cmd']=='Connect']
        assert set(login['tags']) == {'Tracker', 'ArchipeMANU-Reader'}
        assert not any(p['cmd']=='Say' for p in second.packets)
        alice.screenshot(path=str(artifact_dir/'automatic-port-desktop.png'),full_page=True)
        alice.set_viewport_size(dict(width=390,height=844))
        assert alice.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        alice.screenshot(path=str(artifact_dir/'automatic-port-mobile.png'),full_page=True)


def test_opening_round_wakes_official_room_once_and_connects_to_new_port(actors, live_server, artifact_dir):
    alice, bob = actors.alice, actors.bob
    with FakeAP(game=GAME, names=('Alice', 'Bob'), seed='BROWSER_TEST') as server:
        server.announce_joins = True
        def publish(**stage):
            pending = live_server.root / 'live-stage-pending.json'
            pending.write_text(json.dumps(stage), encoding='utf-8')
            pending.replace(live_server.root / 'live-stage.json')

        publish(port=1, paused=True)
        register(alice, 'Alice'); register(bob, 'Bob'); upload_world(alice)
        create_lobby(alice, 'Automatischer Start'); join_lobby(bob, 'Automatischer Start')
        select_game(alice); select_game(bob); mark_ready(alice, 'Alice'); mark_ready(bob, 'Bob')
        alice.reload()
        alice.get_by_role('button', name='Seed generieren', exact=True).click()
        host = generated(alice)
        host.get_by_label('Archipelago-Raum für Live-Statistiken', exact=True).fill(
            'https://archipelago.gg/room/AAECAwQFBgcICQoLDA0ODw')
        host.get_by_role('button', name='Raum verbinden', exact=True).click()
        bob.goto(alice.url)
        for page in (alice, bob):
            expect(page.locator('#console-state')).to_have_text('Archipelago-Server wird gestartet …', timeout=15000)
        bob.screenshot(path=str(artifact_dir / 'room-starting.png'))
        publish(port=server.port, local_ports=[server.port], offset=6)
        for page in (alice, bob):
            expect(page.locator('#console-state')).to_contain_text('Mit Archipelago verbunden', timeout=20000)
            expect(page.locator('#console-log')).to_contain_text('Progression Key')
            expect(page.locator('#console-log')).not_to_contain_text('Alice tracking has joined.')
            expect(page.locator('#console-server-address')).to_have_text(f'archipelago.gg:{server.port}')
        calls = (live_server.root / 'live-api-calls.jsonl').read_text(encoding='utf-8').splitlines()
        assert [json.loads(line)['identifier'] for line in calls if json.loads(line)['endpoint'] == 'wake'] == [
            'AAECAwQFBgcICQoLDA0ODw']
        login, = [packet for packet in server.packets if packet['cmd'] == 'Connect']
        assert set(login['tags']) == {'Tracker', 'ArchipeMANU-Reader'}


def test_missing_login_shows_recovery_and_returns_to_round(actors,artifact_dir):
    from .fixtures import PASSWORD
    page=actors.alice
    register(page,'Alice');upload_world(page)
    create_lobby(page,'Zurück zur Konsole');select_game(page);mark_ready(page,'Alice')
    page.get_by_role('button',name='Seed generieren',exact=True).click()
    host=generated(page)
    host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
    host.get_by_label('Port',exact=True).fill('9')
    host.get_by_role('button',name='Verbindung speichern',exact=True).click()
    page.get_by_label('Nachricht oder Befehl',exact=True).fill('Noch nicht senden')
    page.context.clear_cookies()
    expect(page.locator('#auth-required')).to_be_visible(timeout=15000)
    expect(page.get_by_label('Nachricht oder Befehl',exact=True)).to_have_value('Noch nicht senden')
    expect(page.locator('#console-error')).to_contain_text('Bitte melde dich erneut an')
    for width in (1440,390):
        page.set_viewport_size(dict(width=width,height=1000))
        page.locator('#main-content').evaluate('n=>{n.focus({preventScroll:true});n.blur()}')
        page.evaluate('window.scrollTo(0,0)')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(artifact_dir/f'login-recovery-{width}.png'),full_page=True)
    page.get_by_role('link',name='Erneut anmelden',exact=True).click()
    expect(page.get_by_role('heading',name='Anmelden',exact=True)).to_be_visible()
    page.get_by_label('Benutzername',exact=True).fill('Alice')
    page.get_by_label('Persönliches Passwort',exact=True).fill(PASSWORD)
    page.get_by_role('button',name='Anmelden',exact=True).click()
    expect(page.get_by_role('heading',level=1)).to_have_text('Zurück zur Konsole')
    expect(page.locator('#ap-console')).to_be_visible()
