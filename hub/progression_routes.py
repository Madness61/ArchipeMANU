"""Spoiler-gated seed search and own-slot progression. Old UT routes stay retired."""
from flask import Blueprint, abort, g, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException
from . import auth, console_routes, db, i18n, progression

bp = Blueprint('progression',__name__)
PREFIX = '/sessions/<int:sid>/builds/<int:build_id>/progression'


@bp.errorhandler(HTTPException)
def error(exc):
    if exc.code == 401:
        return auth.login_required_response()
    return jsonify(error=i18n.http_error(exc)),exc.code


@bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def access(sid,bid,reveal=True):
    room, build, own = console_routes.access(sid,bid)
    if reveal and bid not in session.get('progression_spoilers',[]):
        abort(403,'Bitte die Fundort-Spoiler zuerst bewusst freigeben.')
    return room,build,own


@bp.route(PREFIX)
def page(sid,build_id):
    room,build,own = access(sid,build_id,False)
    return render_template('progression.html',room=room,build=build,own=own)


@bp.route(PREFIX+'/consent',methods=['POST'])
def consent(sid,build_id):
    access(sid,build_id,False)
    grants = session.get('progression_spoilers',[])
    grants = [b for b in grants if b!=build_id]
    if request.form.get('reveal') == '1':
        grants.append(build_id)
    session['progression_spoilers'] = grants[-20:]
    return jsonify(revealed=build_id in grants)


@bp.route(PREFIX+'/state')
def state(sid,build_id):
    _,build,_ = access(sid,build_id,False)
    evidence = progression.manifest(build)
    summary,rows = progression.placements(build)
    return jsonify(revealed=build_id in session.get('progression_spoilers',[]),
                   support='partial' if evidence and evidence.get('static',{}).get('state')=='ready' else 'basic',
                   available=rows is not None, static_available=bool(evidence and evidence.get('static',{}).get('state')=='ready'))


@bp.route(PREFIX+'/items')
def items(sid,build_id):
    _,build,own = access(sid,build_id)
    category = request.args.get('category','all')
    owner = request.args.get('owner','all')
    status = request.args.get('status','all')
    if category not in ('all','progression','useful','filler','trap') or owner not in ('all','mine') or status not in ('all','checked','unchecked','unknown'):
        abort(400)
    try:
        page = int(request.args.get('page','1'))
        if page<1:
            raise ValueError()
    except ValueError:
        abort(400)
    return jsonify(progression.find(build,own,request.args.get('q','')[:100],category,owner,status,page))


def own_slot(own):
    name = request.values.get('slot',own[0]['slot'] if len(own)==1 else '')
    slot = next((slot for slot in own if slot['slot']==name),None)
    if not slot:
        abort(403,'Du kannst nur deinen eigenen Spielslot analysieren.')
    return slot


@bp.route(PREFIX+'/analysis',methods=['GET','POST'])
def analysis(sid,build_id):
    _,build,own = access(sid,build_id)
    slot = own_slot(own)
    mode = request.values.get('mode','items')
    if mode not in ('items','goal'):
        abort(400)
    target = None
    kind = request.values.get('target_kind','')
    if kind:
        if kind == 'location':
            try:
                target=dict(kind=kind,id=int(request.values.get('target_id','')))
            except ValueError:
                abort(400)
        elif kind == 'region':
            target=dict(kind=kind,name=request.values.get('target_name','')[:200])
        else:
            abort(400)
    if request.method=='POST':
        limited = auth.consume_attempt('progression-analysis',str(g.user['id']),30)
        if limited:
            return limited
    if target:
        evidence=progression.manifest(build)
        if evidence:
            pid=next((p['id'] for p in evidence['model']['players'] if p['name']==slot['slot']),None)
            valid=(any(l['player']==pid and l['id']==target['id'] for l in evidence['model']['locations'])
                   if target['kind']=='location' else any(r['player']==pid and r['name']==target['name'] for r in evidence['model'].get('regions',[])))
            if not valid:
                abort(400)
    result = progression.job(build,slot,g.user['id'],request.method=='POST',target,mode)
    if result['state']=='ready':
        verified = {(r['finder'],r['location_id']):r for r in progression.find(build,own,owner='mine',limit=0)['rows']}
        for row in result.get('singles',[]) + result.get('combinations',[]):
            for item in row['items']:
                item['placements'] = [verified[(loc['finder'],loc['location_id'])] for loc in item['locations']
                                      if (loc['finder'],loc['location_id']) in verified]
        for row in result.get('necessity',[]):
            row['placement'] = verified.get((row['finder'],row['location_id']))
    # Static sphere positions are theoretical progression, never current reachability.
    evidence = progression.manifest(build)
    if evidence:
        pid = next((p['id'] for p in evidence['model']['players'] if p['name']==slot['slot']),None)
        result['static'] = dict(complete=evidence.get('static',{}).get('complete',False),
            spheres=[dict(number=n+1,unreachable=s['unreachable'],locations=[loc for loc in s['locations'] if loc['player']==pid])
                     for n,s in enumerate(evidence.get('static',{}).get('spheres',[]))])
    result['slot'] = slot['slot']
    return jsonify(result)
