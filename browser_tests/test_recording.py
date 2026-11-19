"""Persistent capture and independent diagnostics through the real browser UI."""
import json
from playwright.sync_api import expect

from .fake_ap import FakeAP
from .fixtures import GAME
from .test_players import generated,register,upload_world,create_lobby,join_lobby,select_game,mark_ready
from .test_preferences import set_preference
from .test_console import configure_room


def test_host_recording_without_open_pages_and_independent_diagnostics(actors,live_server,artifact_dir):
    alice,bob=actors.alice,actors.bob
    with FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST',password='Only in memory') as server:
        register(alice,'Alice');register(bob,'Bob');upload_world(alice)
        create_lobby(alice,'Dauerhafte Aufzeichnung');join_lobby(bob,'Dauerhafte Aufzeichnung')
        select_game(alice);select_game(bob);mark_ready(alice,'Alice');mark_ready(bob,'Bob')
        alice.reload();alice.get_by_role('button',name='Seed generieren',exact=True).click()
        host=generated(alice)
        host.get_by_label('Archipelago-Raum-Link (optional)',exact=True).fill('https://archipelago.gg/room/AAECAwQFBgcICQoLDA0ODw')
        host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
        host.get_by_label('Port',exact=True).fill(str(server.port))
        host.get_by_role('button',name='Verbindung speichern',exact=True).click()
        round_url=alice.url
        configure_room(alice,'Only in memory')
        expect(alice.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS')
        expect(alice.locator('#console-connect')).to_have_count(0)
        expect(alice.locator('#console-log')).to_contain_text('Fundzeit unbekannt')
        # No round page is open while the dedicated recording receives this item.
        alice.goto('about:blank');bob.goto('about:blank')
        packet=dict(cmd='PrintJSON',type='ItemSend',receiving=2,item=dict(item=502,location=1002,player=1,flags=0),data=[])
        server.send(server.clients[0],[packet,packet])
        bob.goto(round_url)
        expect(bob.locator('#console-log')).to_contain_text('Alice → Bob: Potion')
        expect(bob.locator('.console-items')).to_have_count(2)
        expect(bob.locator('.recording-manager')).to_have_count(0)
        expect(bob.locator('#console-connect')).to_have_count(0)
        expect(bob.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS')
        set_preference(bob,'language','en')
        expect(bob.locator('#console-state')).to_have_text('Connected to Archipelago · WS')
        bob.get_by_text('Connection diagnostics',exact=True).click()
        pending=live_server.root/'live-stage-pending.json'
        pending.write_text(json.dumps(dict(offset=61,fail=True)),encoding='utf-8')
        pending.replace(live_server.root/'live-stage.json')
        expect(bob.locator('#console-diagnostics')).to_contain_text('temporarily',timeout=20000)
        expect(bob.locator('#console-state')).to_have_text('Connected to Archipelago · WS')
        expect(bob.locator('#console-state')).to_have_text('Connected to Archipelago · WS')
        expect(bob.locator('#console-diagnostics')).to_contain_text('Unknown')
        expect(bob.locator('#console-diagnostics')).to_contain_text('Next API update')
        for mode in ('dark','light'):
            set_preference(bob,'theme',mode)
            expect(bob.locator('#console-search')).to_have_css('background-color','rgb(248, 250, 255)' if mode=='light' else 'rgb(17, 26, 46)')
            for width in (390,768,1440,2560):
                bob.set_viewport_size(dict(width=width,height=1000))
                assert bob.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                bob.locator('#main-content').evaluate('n=>{n.focus({preventScroll:true});n.blur()}')
                bob.screenshot(path=str(artifact_dir/f'recording-diagnostics-{mode}-{width}.png'),full_page=True)
        bob.route('**/console/data*',lambda route:route.abort())
        expect(bob.locator('#console-diagnostics')).to_contain_text('Unreachable',timeout=10000)
        expect(bob.locator('#console-state')).to_have_text('Connected to Archipelago · WS')
        bob.unroute('**/console/data*')
        expect(bob.locator('#console-diagnostics')).to_contain_text('Reachable',timeout=10000)
        assert len(server.clients)==1
        assert not any(p['cmd'] in ('Say','LocationChecks','StatusUpdate') for p in server.packets)
        pending.write_text(json.dumps(dict(offset=122,advance=True,unknown_goal=True)),encoding='utf-8')
        pending.replace(live_server.root/'live-stage.json')
        bob.locator('[data-round-view="players"]').click()
        expect(bob.locator('[data-round-player="Bob"] [data-player-goal]')).to_have_text('Goal reached',timeout=20000)
        bob.locator('[data-round-player="Alice"]').click()
        expect(bob.locator('#round-player-goal')).to_have_text('Goal status unknown')
        expect(bob.locator('#round-item-events')).to_have_count(0)
        expect(bob.locator('[data-round-view="play"]')).to_be_visible()
        expect(bob.locator('#round-live-status')).not_to_contain_text('Datenstand')
        alice.goto(round_url)
        configure_room(alice,'Only in memory')
        # Host reconfiguration replaces the reader; visitors do not add connections.
        expect(bob.locator('#console-state')).to_have_text('Connected to Archipelago · WS')
        assert len(server.clients)==1



def test_recording_resumes_after_real_isolated_hub_process_restart(actors,live_server,artifact_dir):
    alice,bob=actors.alice,actors.bob
    with FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST') as server:
        register(alice,'Alice');register(bob,'Bob');upload_world(alice)
        create_lobby(alice,'Neustart ohne Datenverlust');join_lobby(bob,'Neustart ohne Datenverlust')
        select_game(alice);select_game(bob);mark_ready(alice,'Alice');mark_ready(bob,'Bob')
        alice.reload();alice.get_by_role('button',name='Seed generieren',exact=True).click()
        host=generated(alice)
        host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
        host.get_by_label('Port',exact=True).fill(str(server.port))
        host.get_by_role('button',name='Verbindung speichern',exact=True).click()
        round_url=alice.url
        expect(alice.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS',timeout=20000)
        expect(alice.locator('.console-items')).to_have_count(1)
        alice.goto('about:blank');bob.goto('about:blank')
        server.history[1].append([502,1002,2,0])
        server.emit_live=False
        live_server.restart()
        bob.goto(round_url)
        expect(bob.locator('#console-state')).to_have_text('Mit Archipelago verbunden · WS',timeout=35000)
        expect(bob.locator('.console-items')).to_have_count(2)
        expect(bob.locator('#console-log')).to_contain_text('Bob → Alice: Potion')
        expect(bob.locator('#console-log')).to_contain_text('Nachträglich bestätigt · Fundzeit unbekannt')
        expect(bob.locator('#console-log')).to_contain_text('Lücke')
        connects=[p for p in server.packets if p['cmd']=='Connect']
        assert len(connects)==2
        assert connects[0]['uuid']==connects[1]['uuid']
        assert not any(p['cmd']=='Say' for p in server.packets)
        bob.screenshot(path=str(artifact_dir/'history-after-hub-restart.png'),full_page=True)
