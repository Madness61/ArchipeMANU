"""Real account settings, two languages/themes and responsive console priorities."""
from playwright.sync_api import expect
from .fake_ap import FakeAP
from .fixtures import GAME
from .test_players import register,upload_world,create_lobby,join_lobby,select_game,mark_ready,generated

def set_preference(page,key,value):
    form=page.locator('.sidebar-footer .appearance-form')
    if form.locator('[name='+key+']').input_value()==value:return
    with page.expect_response(lambda response:response.url.endswith('/preferences') and response.request.method=='POST') as result:
        form.locator('[name='+key+']').select_option(value)
    assert result.value.status==200
    if key=='language':expect(page.locator('html')).to_have_attribute('lang',value)
    else:expect(page.locator('html')).to_have_attribute('data-theme',value)

def test_language_theme_draft_filters_and_responsive_views(actors,artifact_dir):
    a,b=actors.alice,actors.bob
    with FakeAP(game=GAME,names=('Alice','Bob'),seed='BROWSER_TEST') as server:
        register(a,'Alice');register(b,'Bob');upload_world(a)
        lobby=create_lobby(a,'Sprachenrunde');join_lobby(b,'Sprachenrunde')
        select_game(a);select_game(b);mark_ready(a,'Alice');mark_ready(b,'Bob')
        a.reload();a.get_by_role('button',name='Seed generieren',exact=True).click()
        host=generated(a)
        host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
        host.get_by_label('Port',exact=True).fill(str(server.port))
        host.get_by_role('button',name='Verbindung speichern',exact=True).click()
        a.get_by_label('Verbindungsart',exact=True).select_option('ws')
        a.get_by_role('button',name='Mit Archipelago verbinden',exact=True).click()
        expect(a.locator('#console-log')).to_contain_text('Progression Key',timeout=20000)
        a.locator('#console-message').fill('Mein ungesendeter Entwurf')
        a.set_viewport_size(dict(width=1440,height=1000))
        set_preference(a,'language','en')
        expect(a.get_by_role('button',name='Send',exact=True)).to_be_visible()
        expect(a.locator('[data-round-view="play"]')).to_have_text('Console')
        expect(a.locator('[data-round-view="more"]')).to_have_text('More')
        expect(a.locator('#console-message')).to_have_value('Mein ungesendeter Entwurf')
        expect(a.locator('#console-log')).to_contain_text('Bob → Alice: Progression Key',timeout=15000)
        a.locator('#console-kind').select_option('for_me')
        expect(a.locator('.console-for-me')).to_have_count(1)
        a.locator('#console-kind').select_option('from_me')
        expect(a.locator('.console-items')).to_have_count(0)
        a.locator('#console-kind').select_option('all')
        expect(a.locator('.console-for-me')).to_have_count(1)
        expect(b.locator('html')).to_have_attribute('lang','de')
        a.evaluate('window.themeSentinel=123')
        set_preference(a,'theme','light')
        assert a.evaluate('window.themeSentinel')==123
        expect(a.locator('body')).to_have_css('background-color','rgb(241, 244, 251)')
        a.reload()
        expect(a.locator('html')).to_have_attribute('data-theme','light')
        expect(a.locator('#console-message')).to_have_value('Mein ungesendeter Entwurf')
        pages=[('/', 'overview'),('/games','library'),('/profile','profile'),('/admin','admin'),(lobby.split('#')[0],'round')]
        for language in ('de','en'):
            a.set_viewport_size(dict(width=1440,height=1000))
            set_preference(a,'language',language)
            for mode in ('light','dark'):
                a.set_viewport_size(dict(width=1440,height=1000))
                set_preference(a,'theme',mode)
                ratio=a.locator('label').first.evaluate('''node=>{
                  const luminance=rgb=>{const c=rgb.match(/[\\d.]+/g).slice(0,3).map(v=>Number(v)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
                  const a=luminance(getComputedStyle(node).color),b=luminance(getComputedStyle(document.body).backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                }''')
                assert ratio>=4.5,(language,mode,ratio)
                for path,name in pages:
                    a.goto(path)
                    expect(a.locator('html')).to_have_attribute('lang',language)
                    expect(a.locator('html')).to_have_attribute('data-theme',mode)
                    for width in (390,768,1440,2560):
                        a.set_viewport_size(dict(width=width,height=1000))
                        a.locator('#main-content').evaluate('node=>{node.focus({preventScroll:true});node.blur()}')
                        a.evaluate('window.scrollTo(0,0)')
                        assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(language,mode,name,width)
                        a.screenshot(path=str(artifact_dir/f'{name}-{language}-{mode}-{width}.png'),full_page=True)
        a.set_viewport_size(dict(width=1440,height=1000))
        set_preference(a,'theme','system')
        a.emulate_media(color_scheme='light')
        expect(a.locator('body')).to_have_css('background-color','rgb(241, 244, 251)')
        a.emulate_media(color_scheme='dark')
        expect(a.locator('body')).to_have_css('background-color','rgb(13, 19, 35)')
        a.emulate_media(reduced_motion='reduce')
        assert a.locator('body').evaluate('n=>getComputedStyle(n).animationName')=='none'
        assert sum(p.get('cmd')=='Connect' and p.get('name')=='Alice' for p in server.packets)==1
