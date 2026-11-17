"""Two ordinary players collaboratively edit an installation guide."""
from playwright.sync_api import expect
from .test_players import register,upload_world


def test_players_edit_shared_installation_guide_and_see_last_author(actors,artifact_dir):
    a,b=actors.alice,actors.bob
    register(a,'Alice');register(b,'Bob');upload_world(a)
    a.goto('/games/browser_test_world')
    a.get_by_role('link',name='Installationsanleitung bearbeiten',exact=True).click()
    a.get_by_label('Setup-Schritte (Text)',exact=True).fill('Client installieren und mit dem Raum verbinden.')
    a.get_by_role('button',name='Guide speichern',exact=True).click()
    expect(a.locator('.guide-author')).to_contain_text('Alice')
    b.goto('/games/browser_test_world')
    expect(b.locator('.guide-author')).to_contain_text('Alice')
    b.get_by_role('link',name='Installationsanleitung bearbeiten',exact=True).click()
    expect(b.get_by_label('Setup-Schritte (Text)',exact=True)).to_have_value('Client installieren und mit dem Raum verbinden.')
    b.get_by_label('Setup-Schritte (Text)',exact=True).fill('Erst Mod installieren, danach den Client verbinden.')
    b.get_by_label('Offizielle Quelle',exact=True).fill('https://example.org/project/installation')
    b.get_by_label('Mod- oder Client-Download',exact=True).fill('https://example.org/project/releases')
    b.get_by_role('button',name='Guide speichern',exact=True).click()
    expect(b.locator('.guide-author')).to_contain_text('Bob')
    a.reload()
    expect(a.locator('.guide-author')).to_contain_text('Bob')
    expect(a.locator('#game-guide')).to_contain_text('Erst Mod installieren')
    a.set_viewport_size(dict(width=390,height=844))
    assert a.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    expect(a.get_by_role('link',name='Mod-/Client-Download der Gruppe',exact=True)).to_have_attribute('href','https://example.org/project/releases')
    expect(a.get_by_role('link',name='Weitere Informationen der Gruppe',exact=True)).to_have_attribute('href','https://example.org/project/installation')
    a.screenshot(path=str(artifact_dir/'shared-guide-mobile.png'),full_page=True)
