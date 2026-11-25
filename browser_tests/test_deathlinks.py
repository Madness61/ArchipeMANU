"""Live bounces on the shared reader, translations, themes and narrow screens."""
from playwright.sync_api import expect

from .fake_ap import FakeAP
from .fixtures import GAME
from .test_players import register, upload_world, create_lobby, join_lobby, select_game, mark_ready, generated
from .test_preferences import set_preference


def test_deathlink_polling_safe_text_and_responsive_statistics(actors, artifact_dir):
    a, b = actors.alice, actors.bob
    with FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST') as server:
        register(a,'Alice'); register(b,'Bob'); upload_world(a)
        create_lobby(a,'DeathLink evening'); join_lobby(b,'DeathLink evening')
        select_game(a); select_game(b); mark_ready(a,'Alice'); mark_ready(b,'Bob')
        a.reload(); a.get_by_role('button',name='Seed generieren',exact=True).click()
        host = generated(a)
        host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
        host.get_by_label('Port',exact=True).fill(str(server.port))
        host.get_by_role('button',name='Verbindung speichern',exact=True).click()
        expect(a.locator('#console-log')).to_contain_text('Progression Key',timeout=20000)
        a.get_by_role('link',name='Erweiterte Statistiken öffnen',exact=True).click()
        expect(a.locator('#deathlink-total')).to_have_text('0')
        expect(a.locator('#deathlink-history')).to_contain_text('Noch keine DeathLinks beobachtet')
        dashboard = a.url
        # Only the one Tracker receives this packet; no per-viewer AP connection.
        reader = server.clients[0]
        packet = dict(cmd='Bounced',tags=['DeathLink'],data=dict(source='Bob',time=1800000000.125,
                      cause='<img src=x onerror=alert(1)> Bob fell'))
        server.send(reader,[packet,packet,dict(cmd='Bounced',tags=['DeathLink'],
                    data=dict(source='Unknown character',time=1800000001,cause='A long cause '*35))])
        expect(a.locator('#deathlink-total')).to_have_text('2',timeout=15000)
        expect(a.locator('#deathlink-ranking')).to_contain_text('Bob')
        expect(a.locator('#deathlink-unresolved')).to_contain_text('Unknown character')
        expect(a.locator('#deathlink-history')).to_contain_text('<img src=x onerror=alert(1)> Bob fell')
        expect(a.locator('#deathlink-history img')).to_have_count(0)
        b.goto(dashboard)
        expect(b.locator('#deathlink-total')).to_have_text('2')
        for language in ('de','en'):
            set_preference(a,'language',language)
            for theme in ('light','dark'):
                set_preference(a,'theme',theme)
                expect(a.locator('#live-deathlinks h2')).to_have_text('DeathLink-Auswertung' if language=='de' else 'DeathLink statistics')
                for width in (390,1440):
                    a.set_viewport_size(dict(width=width,height=950))
                    a.locator('#live-deathlinks').scroll_into_view_if_needed()
                    assert a.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    a.screenshot(path=str(artifact_dir/f'deathlink-{language}-{theme}-{width}.png'),full_page=True)
        assert not any(p['cmd']=='Bounce' for p in server.packets)
