"""Read-only checks for UI literals which bypass the shared translation system."""
import ast
import json
from pathlib import Path
import re

from scripts.ui_catalog import ROOT, human, messages

_english=json.loads((ROOT/'hub/locales/en.json').read_text(encoding='utf-8'))
_known_translated={value for key,value in messages.items() if key in _english and value!=_english[key]}


def ui_literal(value):
    return human(value) or re.sub(r'\s+',' ',value).strip() in _known_translated

JS_TOKENS = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27')
TRANSLATED = re.compile(r'(?:\.t|\bt)\(\s*$')


def literals(source):
    for token in JS_TOKENS.finditer(source):
        raw = token.group()
        if raw.startswith(('//','/*')):
            continue
        if raw.startswith('`'):
            value = re.sub(r'\$\{[^}]+\}','{value}',raw[1:-1])
        else:
            try:
                value = ast.literal_eval(raw)
            except (ValueError,SyntaxError):
                continue
        yield token,value,bool(TRANSLATED.search(source[max(0,token.start()-60):token.start()]))


def untranslated_js(root=Path('hub/static')):
    for path in root.glob('*.js'):
        if path.name=='logic.js':  # Unserved, explicitly historical code.
            continue
        source=path.read_text(encoding='utf-8')
        for token,value,translated in literals(source):
            if ui_literal(value) and not translated:
                yield f'{path}:{source.count(chr(10),0,token.start())+1}',value


def untranslated_jinja(root=Path('hub/templates')):
    from jinja2 import Environment,nodes
    for path in root.glob('*.html'):
        if path.name=='logic_tracker.html':
            continue
        tree=Environment().parse(path.read_text(encoding='utf-8'))
        translated=set()
        for call in tree.find_all(nodes.Call):
            if isinstance(call.node,nodes.Name) and call.node.name=='_':
                translated.update(id(node) for node in call.find_all(nodes.Const))
        for node in tree.find_all(nodes.Const):
            if isinstance(node.value,str) and id(node) not in translated and ui_literal(node.value):
                yield f'{path}:{node.lineno}',node.value


if __name__=='__main__':
    issues=[*untranslated_js(),*untranslated_jinja()]
    for location,value in issues:
        print(f'{location}: {value}')
    raise SystemExit(bool(issues))
