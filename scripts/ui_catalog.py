"""Maintain stable message IDs and instrument static hub UI text.

Run --write once when onboarding untranslated sources. Never operates on user
content, APWorld schemas, packet values, names or YAML. English is curated separately.
"""
import ast
import html
import json
from pathlib import Path
import re
import sys
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'hub/locales/de.json'
messages=json.loads(DEST.read_text(encoding='utf-8')) if DEST.exists() else {}
known={v:k for k,v in messages.items()}
def remember(value):
    value=re.sub(r'\s+',' ',value).strip()
    if value not in known:
        key='m'+str(max((int(k[1:]) for k in messages),default=0)+1).zfill(4)
        messages[key]=value;known[value]=key
    return value

def human(value):
    return (bool(re.search(r'[A-Za-zÄÖÜäöüß]',value)) and not value.startswith(('http','/','#','.'))
            and not re.fullmatch(r'[\w.-]+\.(html|js|css|json)',value)
            and (bool(re.search(r'[ÄÖÜäöüß]|\b(Dein|Deine|dein|die|Der|der|nicht|noch|Bitte|und|oder|für|werden|wird|Keine|Nur|Alle|Spiel|Spiele|Runde|Speichern|Abbrechen|Offen|Geschlossen|Bereit|Profil|Anmelden|Abmelden|Vorlage|Vorlagen|Suche|Erfolg|Zurücksetzen|Datei|Dateien|Einstellungen|Teilnehmer|Darstellung|Sprache|Dunkel|Hell)\b',value))
                or bool(re.search(r'\b(unbekannt|erreicht|Kopiert|kopiert|aus|ja|nein|Fortschritt|Antworten|Antwort|nicht|vorhanden|Zuletzt|gegebenenfalls|Verbindung|Werte|Anzahl|erfolgreich)\b',value))
                or (' ' in value and re.search(r'[A-ZÄÖÜ]',value[:5]))))

class TemplateText:
    def __init__(self):self.tag=False;self.quote=None;self.tag_text='';self.raw=None
    def data(self,text):
        out=[];plain=[]
        def flush():
            value=''.join(plain);plain.clear()
            if value.strip() and not self.raw and re.search(r'[A-Za-zÄÖÜäöüß]',html.unescape(value)):
                key=remember(html.unescape(value))
                out.append(value[:len(value)-len(value.lstrip())]+'{{ _('+json.dumps(key,ensure_ascii=False)+') }}'+value[len(value.rstrip()):])
            else:out.append(value)
        for c in text:
            if not self.tag and c=='<':
                flush();self.tag=True;self.tag_text='<';out.append(c)
            elif self.tag:
                out.append(c);self.tag_text+=c
                if self.quote:
                    if c==self.quote:self.quote=None
                elif c in ('"',"'"):self.quote=c
                elif c=='>':
                    match=re.match(r'</?([\w-]+)',self.tag_text)
                    if match:
                        name=match[1].lower()
                        if self.tag_text.startswith('</') and self.raw==name:self.raw=None
                        elif name in ('script','style','code','pre','textarea'):self.raw=name
                    self.tag=False
            else:plain.append(c)
        flush()
        value=''.join(out)
        def attribute(m):
            text=html.unescape(m[3])
            if not text or not re.search(r'[A-Za-zÄÖÜäöüß]',text) or text.startswith('name:'):return m[0]
            return m[1]+m[2]+'{{ _('+json.dumps(remember(text),ensure_ascii=False)+') }}'+m[2]
        return re.sub(r'((?:aria-label|placeholder|title)=)([\"\x27])([^{}<>\"\x27]+)\2',attribute,value)

def instrument_template(path):
    source=path.read_text(encoding='utf-8');scanner=TemplateText();out=[]
    for _,kind,value in Environment(keep_trailing_newline=True).lex(source):
        if kind=='data':value=scanner.data(value)
        elif kind=='string':
            try:literal=ast.literal_eval(value)
            except (ValueError,SyntaxError):literal=''
            if isinstance(literal,str) and (literal in known or human(literal)):
                remember(literal)
                if not re.search(r'_\(\s*$',''.join(out[-4:])):value='_('+value+')'
        out.append(value)
    return ''.join(out)

def instrument_js(path):
    source=path.read_text(encoding='utf-8')
    def string(m):
        raw=m[0]
        if raw.startswith(('//','/*')):return raw
        wrapped=bool(re.search(r'(?:\.t|\bt)\(\s*$',source[max(0,m.start()-40):m.start()]))
        if raw.startswith('`'):
            # Preserve interpolation, translate only the hub's surrounding UI text.
            count=[0]
            def hole(_):n=count[0];count[0]+=1;return '{v'+str(n)+'}'
            key=re.sub(r'\$\{[^}]*\}',hole,raw[1:-1])
            if human(key):remember(key);return raw if wrapped else 'window.HUB_I18N.t('+raw+')'
            return raw
        try:literal=ast.literal_eval(raw)
        except (ValueError,SyntaxError):return raw
        if human(literal):
            remember(literal)
            if wrapped or source[m.end():].lstrip().startswith(':'):return raw
            return 'window.HUB_I18N.t('+raw+')'
        return raw
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27',string,source)

if __name__=='__main__':
    write='--write' in sys.argv
    for path in sorted((ROOT/'hub/templates').glob('*.html')):
        if path.name=='logic_tracker.html':continue  # Historical, unserved template.
        result=instrument_template(path)
        if write:path.write_text(result,encoding='utf-8')
    for path in sorted((ROOT/'hub/static').glob('*.js')):
        if path.name=='logic.js':continue
        result=instrument_js(path)
        if write and path.name!='preferences.js':path.write_text(result,encoding='utf-8')
    for path in (ROOT/'hub').glob('*.py'):
        if path.name in ('logic_tracker.py','i18n.py','game_catalog.py'):continue
        tree=ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and (getattr(node.func,'id','') in ('abort','flash','ValueError','APIError','t','_') or getattr(node.func,'attr','') in ('note','t')):
                for arg in node.args:
                    if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and human(arg.value):remember(arg.value)
                    if isinstance(arg,ast.JoinedStr):
                        parts=[];i=0
                        for piece in arg.values:
                            if isinstance(piece,ast.Constant):parts.append(piece.value)
                            else:parts.append('{v'+str(i)+'}');i+=1
                        value=''.join(parts)
                        if human(value):remember(value)
            if isinstance(node,ast.Constant) and isinstance(node.value,str) and re.search(r'[ÄÖÜäöüß]|\b(Dein|Deine|nicht|Bitte|und|oder|werden|wird|Keine|Nur|Alle|Spiel|Spiele|Runde|Vorlage|Vorlagen|Einstellungen|Teilnehmer|unbekannt|erreicht|Fehler|fertig)\b',node.value):
                if not node.value.lstrip().startswith(('SELECT','INSERT','UPDATE','CREATE','DELETE')):remember(node.value)
            if isinstance(node,ast.JoinedStr):
                parts=[];i=0
                for piece in node.values:
                    if isinstance(piece,ast.Constant):parts.append(piece.value)
                    else:parts.append('{v'+str(i)+'}');i+=1
                value=''.join(parts)
                if human(value) and not value.lstrip().startswith(('SELECT','INSERT','UPDATE','DELETE','CREATE','AND ','ALTER ')):remember(value)
    sys.path.insert(0,str(ROOT))
    from hub.game_catalog import CATALOG,SETUP_TYPES,SUPPORT_STATES,HOST_ROM_REQUIRED,_SOURCES
    for info in CATALOG.values():
        for label in info.get('genres',[])+info.get('tags',[]):remember(label)
    for label in [*SETUP_TYPES.values(),*SUPPORT_STATES.values(),*HOST_ROM_REQUIRED.values()]:remember(label)
    for info in _SOURCES.values():
        for link in info.get('links',[]):
            if isinstance(link,dict) and link.get('label'):remember(link['label'])
    from hub.ap_console import COMMANDS
    for _,description in COMMANDS:remember(description)
    remember('Gespeichert.')
    for label in ['Wird vorbereitet','Wird generiert','Generiert','Fehlgeschlagen','Generierung fehlgeschlagen','Vorbereitung','Spielvorgaben','Entsperren','Die Live-Aufzeichnung hat begonnen.','Der Tracker meldet weniger Checks. Ein neuer Verlaufabschnitt beginnt.','{v0} weitere Checks.','{v0} weitere Items gemeldet.','Noch kein Archipelago-Raum verbunden.']:
        remember(label)
    DEST.parent.mkdir(exist_ok=True)
    DEST.write_text(json.dumps(messages,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('UI messages:',len(messages))
