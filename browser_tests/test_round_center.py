"""Complete central UX against inert generator and local AP protocol fixtures."""
import json
from playwright.sync_api import expect

from .fake_ap import FakeAP
from .fixtures import GAME
from .test_players import area,generated,register,upload_world,create_lobby,join_lobby,mark_ready


def test_round_center_standards_files_progress_connection_and_completion(actors,artifact_dir):
    a,b=actors.alice,actors.bob
    with FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST',password='Room secret') as server:
        register(a,'Alice');register(b,'Bob');upload_world(a)
        lobby=create_lobby(a,'Ein gemeinsamer Ort');join_lobby(b,'Ein gemeinsamer Ort')
        for page in (a,b):
            page.get_by_role('combobox',name='Ich spiele:',exact=True).select_option('browser_test_world')
            page.get_by_role('button',name='Standardwerte übernehmen',exact=True).click()
            expect(page.locator('#selection-editor')).to_have_count(0)
            mark_ready(page,'Alice' if page==a else 'Bob')
        a.reload();a.get_by_role('button',name='Seed generieren',exact=True).click()
        host=generated(a)
        host.get_by_label('Archipelago-Raum-Link (optional)',exact=True).fill('https://archipelago.gg/room/AAECAwQFBgcICQoLDA0ODw')
        host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
        host.get_by_label('Port',exact=True).fill(str(server.port))
        host.get_by_role('button',name='Verbindung speichern',exact=True).click()
        a.get_by_role('link',name='Mein Spiel, Dateien & Verbindung',exact=True).click()
        expect(a.locator('#slot-1')).to_have_text('Alice')
        expect(a.locator('#connection')).to_contain_text(f'127.0.0.1:{server.port}')
        # Real clipboard binding, no browser clipboard permission required.
        a.evaluate("window.testCopies=[];Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>window.testCopies.push(value)},configurable:true})")
        a.get_by_role('button',name='Adresse kopieren',exact=False).click()
        assert a.evaluate('window.testCopies')==[f'127.0.0.1:{server.port}']
        expect(a.locator('.personal-file')).to_contain_text('Alice.aptest')
        expect(a.locator('.personal-file')).not_to_contain_text('Bob.aptest')
        with a.expect_download() as download:
            a.get_by_role('link',name='Meine Patchdatei herunterladen',exact=True).click()
        assert download.value.suggested_filename=='Alice.aptest'
        a.get_by_role('link',name='Installationsanleitung öffnen',exact=True).click()
        expect(a.locator('#setup-1')).to_be_visible()
        # Four in-page areas never trigger a document navigation.
        navigations=[]
        a.on('request',lambda req:navigations.append(req.url) if req.is_navigation_request() else None)
        area(a,'Fortschritt')
        expect(a.locator('#round-checks')).to_have_text('2 / 10',timeout=15000)
        expect(a.locator('#round-percent')).to_have_text('20 %')
        expect(a.locator('#round-chart svg')).to_be_visible()
        assert 'SECRET FUTURE LOCATION' not in a.content()
        assert not server.packets
        area(a,'Spielen')
        a.get_by_label('Verbindungsart',exact=True).select_option('ws')
        a.get_by_label('Raumpasswort (optional)',exact=True).fill('Room secret')
        a.get_by_role('button',name='Mit Archipelago verbinden',exact=True).click()
        expect(a.locator('#console-state')).to_contain_text('Mit Archipelago verbunden',timeout=20000)
        expect(a.locator('#console-log')).to_contain_text('Progression Key',timeout=15000)
        assert all(p['cmd'] not in ('LocationChecks','LocationScouts','StatusUpdate','Say') for p in server.packets)
        area(a,'Fortschritt')
        expect(a.locator('#round-next-checks')).to_have_count(0)
        expect(a.locator('#round-go-mode')).to_have_count(0)
        for label in ('Mitspieler','Mehr','Spielen','Fortschritt'):
            area(a,label)
        assert not navigations
        area(a,'Mitspieler')
        expect(a.locator('.round-player')).to_have_count(2)
        a.locator('.round-player').first.get_by_role('button',name='Statistik ansehen',exact=True).click()
        expect(a.locator('.round-player-detail').first).to_contain_text('Empfangene Items: 1')
        for width in (1440,768,390,2560):
            a.set_viewport_size(dict(width=width,height=1000))
            for label in ('Spielen','Fortschritt','Mitspieler','Mehr'):
                area(a,label)
                a.locator('#main-content').evaluate('n=>{n.focus({preventScroll:true});n.blur()}')
                a.evaluate('window.scrollTo(0,0)')
                assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,label)
                a.screenshot(path=str(artifact_dir/f'round-{label}-{width}.png'),full_page=True)
        a.goto('/')
        expect(a.locator('[data-round-id="1"]')).to_have_count(1)
        expect(a.locator('#main-navigation>a')).to_have_count(3)
        b.goto(lobby.split('#')[0])
        b.get_by_role('link',name='Mein Spiel, Dateien & Verbindung',exact=True).click()
        expect(b.locator('#round-host-connection')).to_have_count(0)
        expect(b.locator('#slot-1')).to_have_text('Bob')
        b.get_by_role('button',name='Ich bin fertig',exact=True).click()
        a.goto(lobby.split('#')[0]);a.get_by_role('link',name='Spielabschluss bestätigen',exact=True).click();a.get_by_role('button',name='Ich bin fertig',exact=True).click()
        expect(a.locator('#round-center')).to_have_attribute('data-phase','completed')
        expect(a.locator('#select-game')).to_have_count(0)
        expect(a.locator('#round-host-connection')).to_have_count(0)
        a.goto('/rounds')
        expect(a.locator('[data-round-id="1"]')).to_have_count(1)
        expect(a.locator('[data-round-id="1"]')).to_contain_text('Abgeschlossen')
