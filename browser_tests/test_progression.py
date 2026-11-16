"""One-click finder and explicit spoilers through real APIs; rule UI fixture marked below."""
import json
from playwright.sync_api import expect
from .test_players import register,upload_world,create_lobby,join_lobby,select_game,mark_ready,generated
from .test_preferences import set_preference


def test_global_finder_and_progression_fallback_languages_themes(actors,artifact_dir):
    a,b=actors.alice,actors.bob
    register(a,'Alice');register(b,'Bob');upload_world(a)
    lobby=create_lobby(a,'Progressionsrunde');join_lobby(b,'Progressionsrunde')
    select_game(a);select_game(b);mark_ready(a,'Alice');mark_ready(b,'Bob')
    a.reload();a.get_by_role('button',name='Seed generieren',exact=True).click()
    host=generated(a)
    host.get_by_label('Serveradresse',exact=True).fill('127.0.0.1')
    host.get_by_label('Port',exact=True).fill('38281')
    host.get_by_role('button',name='Verbindung speichern',exact=True).click()
    a.locator('#console-message').fill('Konsole bleibt bedienbar')
    a.get_by_role('button',name='Item suchen',exact=True).click()
    panel=a.locator('#progression-panel')
    expect(panel).to_be_visible()
    expect(panel.locator('#progression-results')).not_to_contain_text('Chest')
    a.get_by_role('button',name='Fundort-Spoiler bewusst freigeben',exact=True).click()
    expect(panel.locator('#progression-results .progression-item')).to_have_count(4)
    panel.get_by_label('Im gesamten Seed suchen',exact=True).fill('Key')
    panel.get_by_role('button',name='Suchen',exact=True).click()
    expect(panel.locator('#progression-results .progression-item')).to_have_count(2)
    expect(panel.locator('#progression-results')).to_contain_text('Bob')
    expect(panel.locator('#progression-results')).to_contain_text('Chest')
    panel.get_by_label('Empfänger',exact=True).select_option('mine')
    expect(panel.locator('#progression-results .progression-item')).to_have_count(1)
    panel.get_by_role('button',name='Meine nächsten Möglichkeiten',exact=True).click()
    expect(panel.locator('#progression-analysis-state')).to_contain_text('älteren Seed')
    panel.get_by_role('button',name='Möglichkeiten berechnen',exact=True).click()
    expect(panel.locator('#progression-analysis-state')).to_contain_text('älteren Seed')
    # No item name was required to request the personal helper.
    panel.get_by_role('button',name='Schließen',exact=True).click()
    expect(a.locator('#console-message')).to_have_value('Konsole bleibt bedienbar')
    b.goto(a.url)
    b.get_by_role('button',name='Item suchen',exact=True).click()
    expect(b.get_by_role('button',name='Fundort-Spoiler bewusst freigeben',exact=True)).to_be_visible()
    b.get_by_role('button',name='Schließen',exact=True).click()

    # Rendering fixture only: CI does not run APWorld code. Actual reconstruction,
    # item gains and necessity are verified by integration_tests/ and core tests.
    response=a.request.get(panel.get_attribute('data-base')+'/items?q=Key&owner=mine').json()
    placed=response['rows'][0]
    recommendation=dict(items=[dict(name='Key',count=1,placements=[placed])],new_checks=[10],new_regions=['Fortress'],goal_reachable=True,target_reached=None)
    def trial(names,checks=(),regions=(),goal=False):
        return dict(items=[dict(name=name,count=1,placements=[dict(placed,item=name)]) for name in names],
                    new_checks=list(checks),new_regions=list(regions),goal_reachable=goal,target_reached=False)
    singles=[recommendation,trial(['Alternative Key'],[10],['Fortress'],True),trial(['Decoration']),
             trial(['Gate A'],[11]),trial(['Gate B'],[12]),trial(['Goal A']),trial(['Goal B'])]
    combinations=[trial(['Key','Decoration'],[10],['Fortress'],True),
                  trial(['Gate A','Gate B'],[11,12,13]),trial(['Goal A','Goal B'],goal=True)]
    rendered=dict(state='ready',observed_at=1794820000,reachable=[dict(id=11,name='Open Check',region='Village')],
        targets=[dict(id=i,name=name,region='Fortress') for i,name in ((10,'New Check'),(11,'Gate A Check'),(12,'Gate B Check'),(13,'Combination Check'))],singles=singles,combinations=combinations,
        singles_tested=7,candidates_total=7,combinations_tested=6,combinations_total=21,
        goal_reachable=False,singles_complete=True,combinations_complete=False,necessity_complete=True,
        necessity=[dict(item='Key',verdict='necessary',placement=placed)],static=dict(spheres=[]))
    a.route('**/progression/analysis*',lambda route:route.fulfill(json=rendered))
    for language in ('de','en'):
        set_preference(a,'language',language)
        for theme in ('light','dark','system'):
            set_preference(a,'theme',theme)
            a.get_by_role('button',name='Was bringt mich weiter?' if language=='de' else 'What helps me progress?',exact=True).click()
            expect(panel.locator('#progression-helpful')).to_contain_text('Key')
            expect(panel.locator('#progression-helpful')).to_contain_text('+1')
            single_section=panel.locator('[data-recommendation-kind="singles"]')
            pair_section=panel.locator('[data-recommendation-kind="combinations"]')
            expect(single_section.locator('.progression-effect-group')).to_have_count(3)
            expect(single_section.locator('.progression-alternatives')).to_have_count(1)
            expect(pair_section.locator('.progression-recommendation')).to_have_count(2)
            expect(pair_section).not_to_contain_text('Key + Decoration')
            expect(pair_section.locator('h4').nth(1)).to_have_text('Goal A + Goal B')
            expect(pair_section.locator('.progression-synergy').last).to_contain_text('+1')
            expect(panel.locator('.progression-coverage')).to_contain_text('6')
            expect(panel.locator('.progression-coverage')).to_contain_text('21')
            panel.locator('.progression-recommendation summary').first.click()
            expect(panel.locator('#progression-helpful')).to_contain_text('Bob')
            for width in (390,1440):
                a.set_viewport_size(dict(width=width,height=920))
                assert panel.evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                a.screenshot(path=str(artifact_dir/f'progression-{language}-{theme}-{width}.png'),full_page=True)
                partial=pair_section.locator('.progression-recommendation').last
                partial.scroll_into_view_if_needed()
                partial.screenshot(path=str(artifact_dir/f'synergy-{language}-{theme}-{width}.png'))
                panel.evaluate('node=>node.scrollTop=0')
            panel.get_by_role('button',name='Spielziel' if language=='de' else 'Game goal',exact=True).click()
            expect(panel.locator('#progression-goals')).to_contain_text('Key')
            panel.locator('#progression-close').click()
    rendered['singles']+= [trial(['Other '+str(i)],[100+i]) for i in range(10)]
    rendered['singles_tested']=rendered['candidates_total']=len(rendered['singles'])
    rendered['combinations_total']=len(rendered['singles'])*(len(rendered['singles'])-1)//2
    a.get_by_role('button',name='What helps me progress?',exact=True).click()
    more=panel.locator('[data-recommendation-kind="singles"] > .progression-more')
    expect(more).to_have_count(1)
    expect(more).not_to_have_attribute('open','')
    more.locator('summary').first.click()
    expect(more).to_have_attribute('open','')
    panel.locator('#progression-close').click()
    # Consent revocation also blocks direct requests, independent of hidden UI.
    a.get_by_role('button',name='Find an item',exact=True).click()
    a.get_by_role('button',name='Hide spoilers again',exact=True).click()
    expect(panel.locator('#progression-content')).to_be_hidden()
    assert a.request.get(panel.get_attribute('data-base')+'/items').status==403
