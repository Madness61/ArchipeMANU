"""Complete central UX against inert generator and local AP protocol fixtures."""
import json
import time
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import expect

from .fake_ap import FakeAP
from .fixtures import GAME
from .test_players import area,generated,register,upload_world,create_lobby,join_lobby,mark_ready
from .test_preferences import set_preference


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
        # The three tabs switch content in place.
        navigations=[]
        a.on('request',lambda req:navigations.append(req.url) if req.is_navigation_request() else None)
        area(a,'Spieler & Items')
        a.locator('.round-team-status summary').click()
        expect(a.locator('#round-checks')).to_have_text('2 / 10',timeout=15000)
        expect(a.locator('#round-percent')).to_have_text('20 %')
        a.locator('.round-team-status summary').click()
        expect(a.locator('[data-round-view]')).to_have_text(['Live','Spieler & Items','Mehr'])
        expect(a.locator('#round-chart, #round-events')).to_have_count(0)
        assert 'SECRET FUTURE LOCATION' not in a.content()
        assert not any(p['cmd'] in ('Say','LocationChecks','LocationScouts','StatusUpdate') for p in server.packets)
        area(a,'Spielen')
        from .test_console import configure_room
        configure_room(a,'Room secret')
        expect(a.locator('#console-state')).to_contain_text('Mit Archipelago verbunden',timeout=20000)
        expect(a.locator('#console-log')).to_contain_text('Progression Key',timeout=15000)
        assert all(p['cmd'] not in ('LocationChecks','LocationScouts','StatusUpdate','Say') for p in server.packets)
        for label in ('Spieler & Items','Mehr','Live','Spieler & Items'):
            area(a,label)
        assert not navigations
        expect(a.locator('[data-round-player]')).to_have_count(2)
        expect(a.locator('#round-player-name')).to_have_text('Alice')
        expect(a.locator('#round-player-checks')).to_have_text('1 / 5 Checks erledigt')
        expect(a.locator('#round-player-percent')).to_have_text('20 %')
        expect(a.locator('#round-item-list')).to_contain_text('Key')
        expect(a.locator('#round-item-list')).not_to_contain_text('Chest')
        assert not a.locator('.round-item-source').count()
        a.locator('[data-round-player="Bob"]').click()
        expect(a.locator('#round-player-name')).to_have_text('Bob')
        expect(a.locator('#round-player-analysis')).to_be_hidden()
        help_tab = a.locator('[data-round-item-view="help"]')
        expect(help_tab).to_be_hidden()
        expect(a.locator('#round-item-list')).to_contain_text('Noch nicht erhalten')
        a.locator('#round-item-spoilers').click()
        expect(a.locator('.round-item-source')).to_have_text('In der Welt von Alice')
        a.locator('#round-item-list summary').click()
        expect(a.locator('#round-item-list')).to_contain_text('Chest')
        expect(a.locator('#round-item-list details')).to_contain_text('Alice')
        expect(help_tab).to_be_visible()
        expect(a.locator('[data-round-item-view="useful"]')).to_be_hidden()
        help_tab.click()
        expect(a.locator('#round-item-list').get_by_role('link', name='Für Alice')).to_be_visible()

        analysis_requests = []
        a.on('request', lambda request: analysis_requests.append((request.method, request.url))
             if urlsplit(request.url).path.endswith('/progression/analysis') else None)

        def cached_analysis(route):
            request = route.request
            if 'overview=1' in request.url:
                route.fulfill(json=dict(state='ready', reachable_count=2, next_check='Old Fortress',
                                        observed_at=time.time(), singles_complete=True))
            else:
                route.continue_()
        a.route('**/progression/analysis?*', cached_analysis)
        a.locator('[data-round-player="Alice"]').click()
        expect(a.locator('#round-analysis-suggestion')).to_have_text('Prüfe Old Fortress.')
        expect(a.locator('#round-analysis-context')).to_contain_text('2 offene Checks laut Spiellogik')
        a.locator('#round-analysis-open').click()
        expect(a.locator('#progression-panel')).to_be_visible()
        a.locator('#progression-close').click()
        assert all(method == 'GET' and 'slot=Alice' in url for method, url in analysis_requests)
        a.locator('[data-round-item-view="received"]').click()
        expect(a.locator('#round-item-result-status')).to_have_text('Noch kein Empfang eines Progression-Items bestätigt.')
        a.locator('[data-round-item-view="open"]').click()
        expect(a.locator('#round-item-list')).to_contain_text('Key')
        expect(a.get_by_role('searchbox', name='Progression-Items suchen')).to_be_hidden()
        for width in (1440,768,390,2560):
            a.set_viewport_size(dict(width=width,height=1000))
            for label in ('Live','Spieler & Items','Mehr'):
                area(a,label)
                a.locator('#main-content').evaluate('n=>{n.focus({preventScroll:true});n.blur()}')
                a.evaluate('window.scrollTo(0,0)')
                assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,label)
                a.screenshot(path=str(artifact_dir/f'round-{label}-{width}.png'),full_page=True)
        a.set_viewport_size(dict(width=1440,height=1000))
        area(a,'Spieler & Items')
        a.locator('#round-item-spoilers').click()
        expect(a.locator('#round-item-list details')).to_have_count(0)
        expect(a.locator('.round-item-source')).to_have_count(0)
        expect(a.locator('#round-analysis-suggestion')).to_have_text('Logikhilfe für dein gemeldetes Inventar.')
        set_preference(a, 'language', 'en')
        expect(a.locator('[data-round-view="players"]')).to_have_text('Players & items')
        set_preference(a, 'theme', 'light')
        a.set_viewport_size(dict(width=390,height=900))
        expect(a.locator('#round-item-list')).to_contain_text('Key')
        a.get_by_role('combobox', name='Select a player').select_option('Bob')
        expect(a.locator('#round-player-name')).to_have_text('Bob')
        expect(a.locator('#round-player-analysis')).to_be_hidden()
        assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        a.screenshot(path=str(artifact_dir/'players-and-items-light-en-390.png'),full_page=True)

        names = ['A long progression item from a far away region'] + [f'Key {index:02}' for index in range(1, 15)]
        def many_items(route):
            args = parse_qs(urlsplit(route.request.url).query)
            query = args.get('q', [''])[0]
            page = int(args['page'][0])
            matches = [name for name in names if query in name]
            rows = [dict(name=name, total=1, states={'found': 1} if name == names[0] else {'unchecked': 1})
                    for name in matches[(page - 1) * 10:page * 10]]
            route.fulfill(json=dict(revealed=False, available=True, counts=dict(open=len(names), received=7, unknown=3),
                                    rows=rows, page=page, pages=max(1, (len(matches) + 9) // 10), total=len(matches)))
        a.route('**/progression/items?*', many_items)
        a.get_by_role('combobox', name='Select a player').select_option('Alice')
        search = a.get_by_role('searchbox', name='Search progression items')
        expect(search).to_have_css('background-color', 'rgb(248, 250, 255)')
        expect(a.locator('#round-item-list').get_by_role('listitem')).to_have_count(10)
        expect(a.locator('#round-item-list')).to_contain_text('Found · receipt unconfirmed')
        assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        a.screenshot(path=str(artifact_dir/'players-and-items-many-light-en-390.png'),full_page=True)
        a.locator('#round-item-next').click()
        expect(a.locator('#round-item-page')).to_have_text('Page 2 of 2')
        search.fill('14')
        matches = a.locator('#round-item-list').get_by_role('listitem')
        expect(matches).to_have_count(1)
        expect(matches.first).to_contain_text('Key 14')
        a.unroute('**/progression/items?*', many_items)
        a.set_viewport_size(dict(width=1440,height=1000))
        set_preference(a, 'theme', 'system')
        set_preference(a, 'language', 'de')
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
        area(a, 'Spielen')
        expect(a.locator('#console-state')).to_have_text('Protokoll archiviert')
        expect(a.locator('#console-log')).to_contain_text('Progression Key')
        expect(a.locator('#console-command')).to_have_count(0)
        a.goto('/rounds')
        expect(a.locator('[data-round-id="1"]')).to_have_count(1)
        expect(a.locator('[data-round-id="1"]')).to_contain_text('Abgeschlossen')
