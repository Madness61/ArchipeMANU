"""Two real browsers and the real bridge against an inert localhost AP protocol server."""
import json
import re

from playwright.sync_api import expect

from .fake_ap import FakeAP
from .fixtures import GAME
from .test_players import area, generated, register, upload_world, create_lobby, join_lobby, select_game, mark_ready


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
        expect(alice.locator('[data-round-view="play"]')).to_have_text('Konsole')
        assert not server.packets  # Viewing the primary console never connects or sends by itself.
        expect(alice.get_by_label("Verbindungsart",exact=True)).to_have_value("auto")
        # This inert localhost fixture intentionally offers unencrypted WS only.
        alice.get_by_label("Verbindungsart",exact=True).select_option("ws")
        alice.get_by_role("button",name="Mit Archipelago verbinden",exact=True).click()
        expect(alice.locator("#console-error")).to_contain_text("Raumpasswort",timeout=15000)
        alice.get_by_label("Raumpasswort (optional)",exact=True).fill("Test room")
        alice.get_by_role("button",name="Mit Archipelago verbinden",exact=True).click()
        expect(alice.locator("#console-state")).to_have_text("Mit Archipelago verbunden · WS",timeout=15000)
        expect(alice.locator("#console-error")).to_be_hidden()
        expect(alice.locator("#console-log")).to_contain_text("Bob → Alice: Progression Key",timeout=15000)
        expect(alice.locator("#console-log")).to_contain_text("Old Fortress - Chest")
        console_url = alice.url
        bob.goto(console_url)
        expect(bob.get_by_label("Dein Slot",exact=True)).to_have_value("Bob")
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
        server.interrupt()
        expect(alice.locator('#console-log')).to_contain_text('Textverbindung wiederhergestellt',timeout=20000)
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
        alice.get_by_role("button",name="Verbindung trennen",exact=True).click()
        expect(alice.locator("#console-state")).to_have_text("Nicht verbunden",timeout=10000)
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
        alice.get_by_label('Verbindungsart',exact=True).select_option('ws')
        alice.get_by_label('Raumpasswort (optional)',exact=True).fill('Test room')
        alice.get_by_role('button',name='Mit Archipelago verbinden',exact=True).click()
        expect(alice.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS')
        expect(alice.locator('.console-items')).to_have_count(1)
        alice.get_by_label('Nachricht oder Befehl',exact=True).fill('Entwurf bleibt beim Portwechsel')
        publish(second.port,61)
        expect(alice.locator('#console-log')).to_contain_text('neuen Port',timeout=20000)
        expect(alice.locator('#console-log')).to_contain_text('Textverbindung wiederhergestellt',timeout=20000)
        expect(alice.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS')
        expect(alice.locator('#console-server-address')).to_have_text(f'archipelago.gg:{second.port}')
        expect(alice.locator('#console-auto-port')).to_be_visible()
        expect(alice.locator('#host-address')).to_have_text(f'archipelago.gg:{second.port}')
        expect(alice.locator('.console-items')).to_have_count(1)
        expect(alice.get_by_label('Nachricht oder Befehl',exact=True)).to_have_value('Entwurf bleibt beim Portwechsel')
        assert len([p for p in second.packets if p['cmd']=='Connect'])==1
        assert not any(p['cmd']=='Say' for p in second.packets)
        alice.screenshot(path=str(artifact_dir/'automatic-port-desktop.png'),full_page=True)
        alice.set_viewport_size(dict(width=390,height=844))
        assert alice.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        alice.screenshot(path=str(artifact_dir/'automatic-port-mobile.png'),full_page=True)


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
