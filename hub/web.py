"""Shared Flask instance and presentation configuration; no route imports."""
from flask import Flask
from hub import db, i18n, game_catalog
app = Flask('hub.app')
app.teardown_appcontext(db.close)
app.jinja_env.globals['_'] = i18n.t
app.jinja_env.globals['http_error'] = i18n.http_error
app.jinja_env.filters['localdate'] = i18n.format_date
app.jinja_env.filters['localnumber'] = i18n.format_number
app.jinja_env.filters['catalog_label'] = game_catalog.label
