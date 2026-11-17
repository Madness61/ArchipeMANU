"""Lobby, build, hosting and download HTTP handlers."""
from __future__ import annotations
import hashlib
import json
import io
import zipfile
from pathlib import Path
from urllib.parse import urlsplit
from flask import abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from hub import ap_bridge, config, db, stats, yamlgen
from hub.services import rounds as mvp
from hub.routes.registry import rounds as bp

@bp.route('/entries/<int:eid>/apworld', methods=['POST'])
def entry_world_version(eid):
    mvp._user()
    entry, room = mvp._entry(eid)
    if room['locked']:
        abort(409)
    chosen = request.form.get('sha256', '').strip()
    options = {v['sha256'] for v in ap_bridge.list_apworld_versions() if v['module'] == entry['game']}
    if chosen and chosen not in options:
        abort(400, 'APWorld-Version nicht vorhanden.')
    mvp.update_open_entry(eid, "selected_apworld_sha=?, ready=0, ready_hash=''", (chosen,))
    flash('Version gewählt. Prüfe danach Optionen und Bereitschaft.', 'info')
    return redirect(url_for('session_view', sid=room['id']))

@bp.route('/seeds')
def seed_list():
    mvp._user()
    rows = db.query('SELECT b.id, b.session_id, b.status, b.created_at, b.completed_at,\n        s.name AS session_name FROM seed_builds b\n        JOIN sessions s ON s.id=b.session_id\n        WHERE (?=1 OR s.created_by=? OR EXISTS (\n            SELECT 1 FROM lobby_members lm WHERE lm.session_id=s.id AND lm.user_id=?\n        ) OR EXISTS (\n            SELECT 1 FROM entries e WHERE e.session_id=s.id AND e.user_id=?\n        )) ORDER BY b.id DESC LIMIT 100', (g.user['is_admin'], g.user['id'], g.user['id'], g.user['id']))
    return render_template('seeds.html', builds=rows)

@bp.route('/lobbies')
@bp.route('/rounds')
def lobby_list():
    mvp._user()
    from hub import rounds
    return render_template('round_directory.html', rooms=rounds.catalog())

@bp.route('/sessions/<int:sid>/join', methods=['POST'])
def join_open_lobby(sid):
    mvp._user()
    room = mvp._session(sid)
    if room['locked']:
        abort(409, 'Die Lobby ist bereits geschlossen.')
    db.execute('INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)', (sid, g.user['id']))
    flash('Du bist der Lobby beigetreten. Wähle jetzt dein Spiel und übernimm die Grundwerte oder passe die Einstellungen an.', 'info')
    return redirect(url_for('session_view', sid=sid))

@bp.route('/sessions/<int:sid>/leave', methods=['POST'])
def leave_lobby(sid):
    mvp._user()
    room = mvp._session(sid)
    if room['locked']:
        abort(409, 'Nach der Seed-Generierung ist die Lobby geschlossen.')
    db.execute('DELETE FROM entries WHERE session_id=? AND user_id=?', (sid, g.user['id']))
    db.execute('DELETE FROM lobby_members WHERE session_id=? AND user_id=?', (sid, g.user['id']))
    flash('Du hast die Lobby verlassen.', 'info')
    return redirect(url_for('mvp.lobby_list'))

@bp.route('/sessions/<int:sid>/members/<int:uid>/remove', methods=['POST'])
def remove_member(sid, uid):
    mvp._user()
    room = mvp._session(sid)
    if not mvp._manager(room):
        abort(403)
    if room['locked']:
        abort(409)
    if uid == room['created_by']:
        abort(400, 'Host kann sich nur selbst über „Lobby verlassen“ entfernen.')
    db.execute('DELETE FROM entries WHERE session_id=? AND user_id=?', (sid, uid))
    db.execute('DELETE FROM lobby_members WHERE session_id=? AND user_id=?', (sid, uid))
    flash('Teilnehmer entfernt. Der Slot blockiert die Generierung nicht mehr.', 'info')
    return redirect(url_for('session_view', sid=sid))

@bp.route('/sessions/<int:sid>/choose')
def choose_game(sid):
    mvp._user()
    room = mvp._session(sid)
    if room['locked']:
        return redirect(url_for('session_view', sid=sid))
    if not mvp._manager(room) and (not db.query('SELECT 1 FROM lobby_members WHERE session_id=? AND user_id=?', (sid, g.user['id']), one=True)):
        return redirect(url_for('mvp.lobby_list'))
    return redirect(url_for('session_view', sid=sid, _anchor='game-selection'))

@bp.route('/sessions/<int:sid>/selection/start', methods=['POST'])
def lobby_selection_start(sid):
    mvp._user()
    room = mvp._session(sid)
    mvp._assert_access(room)
    from hub import lobby_selection
    return lobby_selection.start(room)

@bp.route('/sessions/<int:sid>/selection', methods=['POST'])
def lobby_selection_submit(sid):
    mvp._user()
    from hub import lobby_selection
    return lobby_selection.submit(sid)

@bp.route('/sessions/<int:sid>/invite', methods=['POST'])
def invite_route(sid):
    mvp._user()
    return mvp.invite_create(sid)

@bp.route('/invite/<token>', methods=['GET', 'POST'])
def invite_accept(token):
    if len(token) > 100:
        abort(404)
    digest = hashlib.sha256(token.encode()).hexdigest()
    invite = db.query('SELECT * FROM lobby_invites WHERE token_hash=?', (digest,), one=True)
    if not invite or invite['expires_at'] < mvp.utc_now():
        abort(404, 'Einladung ungültig oder abgelaufen.')
    room = mvp._session(invite['session_id'])
    if not g.user:
        return redirect(url_for('login', next=request.path))
    if room['locked']:
        abort(409, 'Diese Runde nimmt keine neuen Teilnehmer mehr auf.')
    if request.method == 'POST':
        db.execute('INSERT OR IGNORE INTO lobby_members(session_id,user_id) VALUES (?,?)', (room['id'], g.user['id']))
        flash('Du bist jetzt in der Lobby. Wähle ein Spiel aus.', 'info')
        return redirect(url_for('session_view', sid=room['id']))
    return render_template('invite.html', room=room)

@bp.route('/entries/<int:eid>/options', methods=['GET', 'POST'])
def entry_options(eid):
    mvp._user()
    entry, room = mvp._entry(eid)
    if room['locked']:
        abort(409, 'Session ist bereits gesperrt. Für Änderungen eine neue Runde erstellen.')
    schema = ap_bridge.schema(entry['game'])
    if schema is None:
        abort(404, 'Diese APWorld ist nicht verfügbar.')
    issue = ap_bridge.world_error(entry['game'], entry['selected_apworld_sha'])
    if issue:
        abort(409, issue)
    from hub.services.selection import entry_preset, user_values, session_entries, entry_yaml
    _, template_values, found, requirements = entry_preset(schema, entry)
    overrides = db.loads(entry['option_overrides'])
    owner = db.query('SELECT * FROM users WHERE id=?', (entry['user_id'],), one=True)
    baseline = user_values(schema, template_values, owner)
    effective = user_values(schema, template_values, owner, overrides)
    errors = yamlgen.validate_values(schema, effective)
    errors.update(yamlgen.validate_requirements(schema, requirements, ap_bridge.index().get('ap_version', '0.0.0')))
    if not found:
        errors['_template'] = 'Die gewählte Vorlage fehlt oder wurde verändert. Bitte eine gültige Vorlage wählen.'
    pending = False
    if request.method == 'POST':
        if request.form.get('_action') == 'reset':
            updated, field_errors = ({}, yamlgen.validate_values(schema, baseline))
        else:
            updated, field_errors = yamlgen.parse_lobby_form(schema, request.form, overrides, baseline)
        errors = {k: v for k, v in errors.items() if k in ('_template', 'requires')}
        errors.update(field_errors)
        pending = True
        if not errors and request.form.get('_action') != 'preview' and (not request.form.get('_reset_option')):
            mvp.update_open_entry(eid, "option_overrides=?, ready=0, ready_hash=''", (db.dumps(updated),))
            flash('Deine Einstellungen wurden gespeichert; bitte erneut als bereit markieren.', 'info')
            return redirect(url_for('session_view', sid=room['id']))
        effective = user_values(schema, template_values, owner, updated)
        if errors:
            flash('Bitte fehlerhafte Optionen korrigieren. Es wurde nichts gespeichert.', 'error')
    groups = {}
    expert = request.args.get('expert') == '1'
    for option in schema['options']:
        if expert or option['key'] in overrides or effective.get(option['key']) != option.get('default') or (option.get('simple') and option.get('group') != 'Item & Location Options' and (option.get('kind') != 'raw')):
            groups.setdefault(option['group'], []).append(option)
    selected = next((e for e in session_entries(room['id']) if e['id'] == eid))
    selected['values'] = effective
    yaml_preview = entry_yaml(selected, schema, ap_bridge.index().get('ap_version', '0.0.0')) if not errors else ''
    return render_template('entry_options.html', entry=entry, room=room, schema=schema, baseline=baseline, groups=groups, values=effective, errors=errors, yg=yamlgen, expert=expert, yaml_preview=yaml_preview, pending=pending, lobby=True)

@bp.route('/entries/<int:eid>/ready', methods=['POST'])
def entry_ready(eid):
    mvp._user()
    entry, room = mvp._entry(eid)
    if entry['user_id'] != g.user['id']:
        abort(403, 'Nur der Slot-Besitzer kann sich bereit melden.')
    if room['locked']:
        abort(409)
    new = request.form.get('ready') == '1'
    if new:
        schema = ap_bridge.schema(entry['game'])
        if not schema:
            flash('Die APWorld ist nicht installiert.', 'error')
            return redirect(url_for('session_view', sid=room['id']))
        from hub.services.selection import entry_preset, capture_template, session_entries
        if not entry['template_snapshot']:
            try:
                snapshot = capture_template(schema, entry['template_ref'])
            except ValueError as exc:
                flash(str(exc), 'error')
                return redirect(url_for('session_view', sid=room['id']))
            mvp.update_open_entry(eid, 'template_snapshot=?', (snapshot,))
        selected = next((e for e in session_entries(room['id']) if e['id'] == eid))
        found = selected['template_found']
        if not found:
            flash('Die ausgewählte Vorlage existiert nicht mehr.', 'error')
            return redirect(url_for('session_view', sid=room['id']))
        errors = yamlgen.validate_values(schema, selected['values'])
        errors.update(yamlgen.validate_requirements(schema, selected['requirements'], ap_bridge.index().get('ap_version', '0.0.0')))
        if errors:
            flash('Optionen ungültig: ' + '; '.join((f'{k}: {v}' for k, v in errors.items()))[:700], 'error')
            return redirect(url_for('mvp.entry_options', eid=eid))
    fingerprint = ''
    if new:
        from hub.services.selection import session_entries
        selected = next((e for e in session_entries(room['id']) if e['id'] == eid))
        if selected['world_error']:
            flash(selected['world_error'], 'error')
            return redirect(url_for('session_view', sid=room['id']))
        fingerprint = mvp.slot_fingerprint(selected)
    mvp.update_open_entry(eid, 'ready=?, ready_hash=?', (int(new), fingerprint))
    return redirect(url_for('session_view', sid=room['id']))

@bp.route('/active-lobby')
def active_lobby():
    mvp._user()
    connections = mvp.active_connections()
    if len(connections) == 1:
        return redirect(url_for('mvp.play_page', sid=connections[0]['session_id'], build_id=connections[0]['build_id']))
    return render_template('active_lobbies.html', connections=connections)

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/finish', methods=['POST'])
def finish_game(sid, build_id):
    mvp._assert_access(mvp._session(sid))
    if request.form.get('finished') not in ('0', '1'):
        abort(400, 'Bitte den Spielstatus ausdrücklich bestätigen oder zurücknehmen.')
    with mvp._LOCK:
        conn = db.get()
        conn.execute('BEGIN IMMEDIATE')
        try:
            build = db.query('SELECT * FROM seed_builds WHERE id=? AND session_id=?', (build_id, sid), one=True)
            if not build:
                abort(404)
            state = mvp.completion_state(build)
            if not state['own'] or state['own']['deleted']:
                abort(403, 'Nur Spieler mit eigenem Slot können ihr Spielziel bestätigen.')
            if build['status'] != 'succeeded' or not db.query('SELECT 1 FROM hosted_rooms WHERE build_id=?', (build_id,), one=True):
                abort(409, 'Die Runde muss zuerst generiert und ihre Verbindung eingerichtet werden.')
            if not build['completed_at']:
                if request.form.get('finished') == '0':
                    conn.execute('DELETE FROM seed_completions WHERE build_id=? AND user_id=?', (build_id, g.user['id']))
                else:
                    conn.execute('INSERT OR IGNORE INTO seed_completions(build_id,user_id,finished_at) VALUES (?,?,?)', (build_id, g.user['id'], mvp.utc_now()))
                state = mvp.completion_state(build)
                if state['total'] and state['finished_count'] == state['total']:
                    now = mvp.utc_now()
                    conn.execute('UPDATE seed_builds SET completed_at=? WHERE id=?', (now, build_id))
                    conn.execute("UPDATE sessions SET completed_at=?,locked=1 WHERE id=? AND locked=1\n                        AND ?=(SELECT MAX(id) FROM seed_builds WHERE session_id=? AND status IN ('queued','running','succeeded'))\n                        AND ?=(SELECT h.build_id FROM hosted_rooms h JOIN seed_builds b ON b.id=h.build_id\n                            WHERE b.session_id=? ORDER BY h.id DESC LIMIT 1)", (now, sid, build_id, sid, build_id, sid))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    flash('Dein Spielstatus wurde gespeichert.', 'info')
    return redirect(url_for('mvp.play_page', sid=sid, build_id=build_id, _anchor='completion'))

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/status')
def build_status(sid, build_id):
    mvp._assert_access(mvp._session(sid))
    row = db.query('SELECT * FROM seed_builds WHERE id=? AND session_id=?', (build_id, sid), one=True)
    if row is None:
        abort(404)
    return jsonify({'status': row['status'], 'log': row['log'][-9000:]})

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/download')
def build_download(sid, build_id):
    mvp._assert_access(mvp._session(sid))
    row = db.query('SELECT * FROM seed_builds WHERE id=? AND session_id=?', (build_id, sid), one=True)
    if not row or row['status'] != 'succeeded':
        abort(404)
    path = config.SESSIONS / '_seeds' / str(build_id) / 'output' / row['zip_name']
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=row['zip_name'])

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/assets/<int:file_index>')
def build_asset(sid, build_id, file_index):
    mvp._assert_access(mvp._session(sid))
    build = db.query('SELECT * FROM seed_builds WHERE id=? AND session_id=?', (build_id, sid), one=True)
    if not build or build['status'] != 'succeeded':
        abort(404)
    allowed = {entry['index']: entry for entry in mvp.artifact_files(build_id, build['zip_name'])}
    if file_index not in allowed:
        abort(404)
    archive_path = config.SESSIONS / '_seeds' / str(build_id) / 'output' / build['zip_name']
    with zipfile.ZipFile(archive_path) as archive:
        payload = archive.read(archive.infolist()[file_index])
    safe_name = Path(allowed[file_index]['name']).name[:150]
    return send_file(io.BytesIO(payload), as_attachment=True, download_name=safe_name, mimetype='application/octet-stream')

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/hosting', methods=['POST'])
def save_hosting(sid, build_id):
    from hub import live_api, live_store
    room = mvp._session(sid)
    if not mvp._manager(room):
        abort(403)
    build = db.query('SELECT * FROM seed_builds WHERE session_id=? AND id=?', (sid, build_id), one=True)
    if not build or build['status'] != 'succeeded':
        abort(409, 'Nur erfolgreiche Seeds können gehostet werden.')
    try:
        link, host, port = mvp.parse_room_form(request.form)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('session_view', sid=sid, _anchor=f'hosting-{build_id}'))
    with mvp._LOCK:
        conn = db.get()
        try:
            conn.execute('BEGIN IMMEDIATE')
            current = db.query('SELECT completed_at FROM seed_builds WHERE id=?', (build_id,), one=True)
            if not current or current['completed_at']:
                abort(409, 'Dieser Seed ist abgeschlossen. Für eine neue Runde einen neuen Seed generieren.')
            conn.execute('INSERT INTO hosted_rooms(build_id,room_url,host,port,confirmed,entered_by,created_at)\n                         VALUES (?,?,?,?,?,?,?)', (build_id, link, host, port, int(request.form.get('confirmed') == '1'), g.user['id'], mvp.utc_now()))
            try:
                live_api.room_id(link)
            except ValueError:
                conn.execute('UPDATE live_rooms SET auto_host=0 WHERE build_id=?', (build_id,))
            else:
                live_store.attach(build_id, link, g.user['id'], connection=conn, auto_host=live_store.official_address(link, host) and request.form.get('manual_port') != '1')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    flash('Verbindung gespeichert. Alle Teilnehmer finden sie unter „Meine Runden“ direkt in eurer Rundenzentrale.', 'info')
    from hub import live_routes
    live_routes.collector()
    return redirect(url_for('mvp.play_page', sid=sid, build_id=build_id))

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/stats')
def build_stats(sid, build_id):
    from hub import live_store
    room = mvp._session(sid)
    mvp._assert_access(room)
    build = db.query('SELECT * FROM seed_builds WHERE id=? AND session_id=?', (build_id, sid), one=True)
    if not build:
        abort(404)
    metadata = json.loads(build['snapshot'])
    payload = mvp._build_distribution(build, metadata)
    placements = mvp._build_placements(build, payload)
    return render_template('seed_stats.html', room=room, build=build, hosted=db.query('SELECT * FROM hosted_rooms WHERE build_id=? ORDER BY id DESC LIMIT 1', (build_id,), one=True), live_connection=live_store.current(build_id), stats=payload, race=bool(metadata.get('race')), overview=stats.game_overview(payload) if payload else [], progression=stats.progression_items(payload, placements) if placements is not None else [], progression_available=placements is not None, reveal=request.args.get('spoilers') == '1')

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/stats/progression/<int:placement_id>')
def reveal_progression_world(sid, build_id, placement_id):
    room = mvp._session(sid)
    mvp._assert_access(room)
    build = db.query('SELECT * FROM seed_builds WHERE id=? AND session_id=?', (build_id, sid), one=True)
    if not build:
        abort(404)
    metadata = json.loads(build['snapshot'])
    if metadata.get('race'):
        abort(403, 'Im Race-Modus sind Spoiler gesperrt.')
    distribution = mvp._build_distribution(build, metadata)
    placements = mvp._build_placements(build, distribution)
    if placements is None or placement_id >= len(placements) or placements[placement_id]['category'] != 'progression':
        abort(404, 'Für dieses Item sind keine verifizierten Progression-Daten verfügbar.')
    worlds = stats.progression_worlds(distribution, placements, placement_id)
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(worlds=worlds)
    return render_template('progression_world.html', room=room, build=build, item=placements[placement_id], worlds=worlds)

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/stats/items/<int:player_id>')
def build_item_details(sid, build_id, player_id):
    room = mvp._session(sid)
    mvp._assert_access(room)
    build = db.query('SELECT * FROM seed_builds WHERE id=? AND session_id=?', (build_id, sid), one=True)
    if not build:
        abort(404)
    metadata = json.loads(build['snapshot'])
    if metadata.get('race'):
        abort(403, 'Im Race-Modus sind Spoiler gesperrt.')
    if build['status'] != 'succeeded':
        abort(404)
    distribution = mvp._build_distribution(build, metadata)
    if distribution is None:
        abort(404)
    players = {p['id']: p for p in distribution['players']}
    if player_id not in players:
        abort(404)
    direction = request.args.get('direction', 'recipient')
    if direction not in ('recipient', 'finder'):
        abort(400)
    search = request.args.get('q', '').strip()[:100]
    try:
        page = max(1, int(request.args.get('page', '1')))
    except ValueError:
        abort(400)
    placements = mvp._build_placements(build, distribution)
    matches = [p for p in placements or [] if p[direction] == player_id and search.casefold() in (p['item'] + ' ' + p['location'] + ' ' + players[p['finder']]['name'] + ' ' + players[p['recipient']]['name']).casefold()]
    pages = max(1, (len(matches) + 49) // 50)
    page = min(page, pages)
    return render_template('seed_items.html', room=room, build=build, player=players[player_id], players=players, available=placements is not None, rows=matches[(page - 1) * 50:page * 50], total=len(matches), page=page, pages=pages, direction=direction, q=search)

@bp.route('/sessions/<int:sid>/builds/<int:build_id>/play')
def play_page(sid, build_id):
    from hub.routes.lobbies import session_view
    return session_view(sid, build_id=build_id)

@bp.route('/admin/guides/<slug>', methods=['GET', 'POST'])
@bp.route('/games/<slug>/guide', methods=['GET', 'POST'])
def guide_edit(slug):
    from hub import community
    from hub.services import guides
    user = mvp._user()
    schema = ap_bridge.schema(slug)
    installed = bool(schema)
    if not schema:
        item = next((item for item in community.all_games() if item['slug']==slug),None)
        if item is None:
            abort(404)
        schema = dict(slug=slug,game=item['name'])
    old = guides.get(slug)
    if request.method == 'POST':

        def field(k, n):
            return request.form.get(k, '').strip()[:n]
        url = field('source_url', 450)
        mod = field('mod_url', 450)
        for candidate in (url, mod):
            if candidate:
                try:
                    parsed = urlsplit(candidate)
                    valid = parsed.scheme in ('https', 'http') and bool(parsed.netloc)
                except ValueError:
                    valid = False
                if not valid:
                    abort(400, 'Nur vollständige HTTP(S)-Links verwenden.')
        guides.save(slug,dict(verified_version=field('verified_version',100),game_version=field('game_version',100),
                             mod_url=mod,source_url=url,steps=field('steps',8000),trouble=field('trouble',4000)),user,mvp.utc_now())
        flash('Guide gespeichert.', 'info')
        return redirect(url_for('game' if installed else 'game_setup', slug=slug))
    return render_template('guide_edit.html', schema=schema, guide=old,
                           back_url=url_for('game' if installed else 'game_setup',slug=slug))
