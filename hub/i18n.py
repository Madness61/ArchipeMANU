"""Shared UI messages and account appearance preferences; never translate AP data."""
import json
import re
from pathlib import Path
from flask import g, has_request_context, request
from . import db

CATALOG_PATH = Path(__file__).with_name('locales') / 'en.json'
SOURCE_PATH = CATALOG_PATH.with_name('de.json')
SOURCE = json.loads(SOURCE_PATH.read_text(encoding='utf-8')) if SOURCE_PATH.exists() else {}
ENGLISH = json.loads(CATALOG_PATH.read_text(encoding='utf-8')) if CATALOG_PATH.exists() else {}
MESSAGES = {value:ENGLISH[key] for key,value in SOURCE.items() if key in ENGLISH}
PATTERNS=[]
for original, english in MESSAGES.items():
    if re.search(r'\{v\d+\}', original):
        parts=re.split(r'(\{v\d+\})',original)
        fields=[part[1:-1] for part in parts if re.fullmatch(r'\{v\d+\}',part)]
        pattern='^'+''.join('(.*?)' if re.fullmatch(r'\{v\d+\}',part) else re.escape(part) for part in parts)+'$'
        PATTERNS.append(dict(pattern=pattern,fields=fields,text=english))
COMPILED=[(re.compile(row['pattern'],re.S),row) for row in PATTERNS]

def preferences():
    if has_request_context() and hasattr(g,'interface_preferences'):
        return g.interface_preferences
    user = getattr(g, 'user', None) if has_request_context() else None
    saved = db.loads(user['overrides']).get('_interface', {}) if user else {}
    if not isinstance(saved, dict):
        saved = {}
    language = saved.get('language', request.cookies.get('ui_language','de') if has_request_context() and not user else 'de')
    theme = saved.get('theme', request.cookies.get('ui_theme','dark') if has_request_context() and not user else 'dark')
    result=dict(language=language if language in ('de','en') else 'de', theme=theme if theme in ('light','dark','system') else 'dark')
    if has_request_context():
        g.interface_preferences=result
    return result

def language():
    return preferences()['language']

def t(message, **values):
    if not isinstance(message, str):
        return message
    key = re.sub(r'\s+', ' ', message).strip()
    translated = MESSAGES.get(key, key) if language() == 'en' else key
    found=key in MESSAGES
    fields={}
    if language()=='en' and key not in MESSAGES and len(key)<=12000:
        for regex,row in COMPILED:
            match=regex.fullmatch(message.strip())
            if match:
                found=True
                translated=row['text']
                fields.update(zip(row['fields'],match.groups()))
                break
    # Format only explicit, named placeholders. Braces in user values remain data.
    fields.update(values)
    def substitute(text):
        return re.sub(r'\{(\w+)\}',lambda match:str(fields[match[1]]) if match[1] in fields else match[0],text)
    translated=substitute(translated)
    if language()=='de':
        return substitute(message)
    return message[:len(message)-len(message.lstrip())]+translated+message[len(message.rstrip()):] if found else message

def error_messages(value):
    if isinstance(value, str):
        return t(value)
    if isinstance(value, list):
        return [error_messages(v) for v in value]
    if isinstance(value, dict):
        return {k:error_messages(v) for k,v in value.items()}
    return value

def format_date(value):
    from datetime import datetime, timezone
    from markupsafe import Markup, escape
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError):return value
    label=parsed.strftime('%d/%m/%Y %H:%M' if language()=='en' else '%d.%m.%Y %H:%M')
    return Markup('<time data-local-date datetime="{}">{}</time>').format(escape(parsed.isoformat()),escape(label))

def format_number(value):
    if type(value) is int:
        return format(value,',').replace(',','.') if language()=='de' else format(value,',')
    if type(value) is float:
        return format(value,',.1f').translate(str.maketrans('.,',',.')) if language()=='de' else format(value,',.1f')
    return value
