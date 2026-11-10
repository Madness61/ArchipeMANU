"""Two real browsers and the real bridge against an inert localhost AP protocol server."""
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
        expect(alice.locator("#console-log")).to_contain_text("Bob → Alice: Progression Key")
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
