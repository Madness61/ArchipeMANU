/* One round surface. All mutations still use the existing authenticated APIs. */
(() => {
  const root = document.getElementById('round-center');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const nav = [...root.querySelectorAll('[data-round-view]')];
  const panels = [...root.querySelectorAll('[data-round-panel]')];
  root.querySelectorAll('[data-player-name]').forEach(card=>card.style.setProperty('--player',window.HUB_UI.playerColor(card.dataset.playerName)));
  const el = (tag, text, cls) => { const n=document.createElement(tag); if(text!=null)n.textContent=text; if(cls)n.className=cls; return n; };
  const value = v => v == null ? '—' : typeof v==='number'?v.toLocaleString(window.HUB_I18N.locale):String(v);
  const pct = v => v == null ? '—' : v.toLocaleString(window.HUB_I18N.locale,{maximumFractionDigits:1})+' %';
  let view='play', liveBusy=false;
  async function api(url, body) {
    const response=await fetch(url,{cache:'no-store',...(body ? {method:'POST',headers:{'X-CSRF-Token':root.dataset.csrf},body:new URLSearchParams(body)} : {})});
    const data=await response.json().catch(()=>({error:window.HUB_I18N.t('Die Antwort konnte nicht gelesen werden. Bitte gegebenenfalls neu anmelden.')}));
    if(response.status===401)window.HUB_AUTH_REQUIRED?.(data.login_url);
    if(!response.ok)throw new Error(data.error||window.HUB_I18N.t('Die Anfrage konnte nicht abgeschlossen werden.'));
    return data;
  }
  function openView() {
    const hash=decodeURIComponent(location.hash.slice(1)), target=$(hash);
    view=panels.some(p=>p.dataset.roundPanel===hash) ? hash : target?.closest('[data-round-panel]')?.dataset.roundPanel || 'play';
    panels.forEach(p=>{p.hidden=p.dataset.roundPanel!==view;});
    nav.forEach(a=>{if(a.dataset.roundView===view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    if(target){let parent=target.closest('details');while(parent){parent.open=true;parent=parent.parentElement?.closest('details');}}
    if(target && !panels.includes(target))requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
    if(['progress','players'].includes(view)) loadLive();
  }
  window.addEventListener('hashchange',openView);
  nav.forEach((a,index)=>a.addEventListener('keydown',event=>{
    if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;
    event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?nav.length-1:(index+(event.key==='ArrowRight'?1:-1)+nav.length)%nav.length;
    nav[next].focus();nav[next].click();
  }));
  root.addEventListener('click',event=>{
    const setup=event.target.closest('[data-show-setup]');
    if(setup){event.preventDefault();const box=$(setup.dataset.showSetup);box.hidden=!box.hidden;setup.setAttribute('aria-expanded',String(!box.hidden));if(!box.hidden)box.scrollIntoView({block:'nearest'});}
    if(event.target.closest('[data-round-refresh]')) loadLive();
    const button=event.target.closest('[data-player-detail]');
    if(button){const card=button.closest('[data-player-name]'),detail=card.querySelector('.round-player-detail');detail.hidden=!detail.hidden;button.setAttribute('aria-expanded',String(!detail.hidden));button.textContent=detail.hidden?window.HUB_I18N.t('Statistik ansehen'):window.HUB_I18N.t('Statistik schließen');}
  });
  function chart(history) {
    const box=$('round-chart');box.replaceChildren();
    if(!history?.length){box.append(el('p',window.HUB_I18N.t('Noch keine aufgezeichneten Datenpunkte.'),'muted small'));return;}
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 800 160');svg.setAttribute('role','img');svg.setAttribute('aria-label',window.HUB_I18N.t('Gemeldeter Gesamtfortschritt im Verlauf'));
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=window.HUB_I18N.t('Gemeldeter Gesamtfortschritt im Verlauf');svg.append(title);
    const start=Date.parse(history[0].at),end=Date.parse(history.at(-1).at),span=end-start||1;
    let points=[],segment=null;
    const flush=()=>{if(!points.length)return;const line=document.createElementNS(svg.namespaceURI,'polyline');line.setAttribute('points',points.join(' '));line.setAttribute('class','round-chart-line');svg.append(line);points=[];};
    for(const p of history){if(p.segment!==segment || p.progress==null)flush();segment=p.segment;if(p.progress!=null){const x=20+760*(Date.parse(p.at)-start)/span,y=140-120*Math.max(0,Math.min(100,p.progress))/100;points.push(x+','+y);const dot=document.createElementNS(svg.namespaceURI,'circle');dot.setAttribute('cx',x);dot.setAttribute('cy',y);dot.setAttribute('r','3');const tip=document.createElementNS(svg.namespaceURI,'title');tip.textContent=new Date(p.at).toLocaleString(window.HUB_I18N.locale)+' · '+pct(p.progress)+' · '+value(p.checks)+window.HUB_I18N.t(' Checks');dot.append(tip);svg.append(dot);}}
    flush();box.append(svg,el('p',new Date(history[0].at).toLocaleString(window.HUB_I18N.locale)+' – '+new Date(history.at(-1).at).toLocaleString(window.HUB_I18N.locale),'small muted'));
  }
  function renderLive(data) {
    const m=data.metrics;
    $('round-live-status').textContent=data.error ? data.error+' '+window.HUB_I18N.t('Der letzte erfolgreiche Datenstand bleibt sichtbar.') : data.updated_at ? (data.stale?window.HUB_I18N.t('Veralteter Datenstand · '):window.HUB_I18N.t('Zuletzt gemeldet · '))+new Date(data.updated_at).toLocaleString(window.HUB_I18N.locale) : window.HUB_I18N.t('Der erste Datenstand wird noch abgerufen.');
    if(data.seed_matches===false)$('round-live-status').textContent+=window.HUB_I18N.t(' Achtung: Spieler oder Spiele des Raums weichen vom lokalen Seed ab.');
    $('round-checks').textContent=m ? value(m.checks)+' / '+value(m.total) : '—';
    $('round-percent').textContent=pct(m?.progress);
    $('round-goals').textContent=m ? value(m.goals)+' / '+value(m.known_goals) : '—';
    $('round-total-bar').style.width=Math.max(0,Math.min(100,m?.progress||0))+'%';
    const ownNames=JSON.parse(root.dataset.ownSlots||'[]');
    const own=(m?.players||[]).filter(p=>ownNames.includes(p.name));
    $('round-own-checks').textContent=own.length && data.seed_matches!==false && own.every(p=>p.checks!=null) ? value(own.reduce((sum,p)=>sum+p.checks,0)) : '—';
    document.querySelectorAll('[data-player-name]').forEach(card=>{
      card.style.setProperty('--player',window.HUB_UI.playerColor(card.dataset.playerName));
      const p=(m?.players||[]).find(p=>p.name===card.dataset.playerName&&p.game===card.dataset.playerGame);
      card.querySelector('[data-player-summary]').textContent=p ? value(p.checks)+' / '+value(p.total)+window.HUB_I18N.t(' Checks · ')+pct(p.progress)+(p.goal?window.HUB_I18N.t(' · Ziel erreicht'):'') : window.HUB_I18N.t('Noch kein gemeldeter Fortschritt');
      card.querySelector('[data-player-bar]').style.width=Math.max(0,Math.min(100,p?.progress||0))+'%';
      const detail=card.querySelector('.round-player-detail');detail.replaceChildren(el('p',p ? window.HUB_I18N.t('Empfangene Items: ')+value(p.received)+window.HUB_I18N.t(' · Ziel: ')+(p.goal==null?window.HUB_I18N.t('unbekannt'):p.goal?window.HUB_I18N.t('erreicht'):window.HUB_I18N.t('noch nicht gemeldet')) : window.HUB_I18N.t('Für diesen Spieler liegen noch keine passenden Daten vor.'),'small'));
      if(p?.activity)detail.append(el('p',window.HUB_I18N.t('Letzte vom Tracker gemeldete Aktivität: ')+new Date(p.activity).toLocaleString(window.HUB_I18N.locale)+'. '+window.HUB_I18N.t('Keine Bestätigung einer aktuellen Verbindung.'),'small muted'));
    });
    chart(data.history);
    $('round-events').replaceChildren(...((data.events||[]).slice(0,8).map(e=>el('li',new Date(e.at).toLocaleTimeString(window.HUB_I18N.locale)+' · '+e.text,'small'))));
    if(!$('round-events').children.length)$('round-events').append(el('li',window.HUB_I18N.t('Noch keine Ereignisse aufgezeichnet.'),'muted small'));
  }
  async function loadLive() {
    if(!root.dataset.live||liveBusy)return;liveBusy=true;
    try{renderLive(await api(root.dataset.live));}
    catch(error){if($('round-live-status'))$('round-live-status').textContent=error.message;}
    finally{liveBusy=false;}
  }
  async function poll(){if(!document.hidden&&['progress','players'].includes(view)) await loadLive();setTimeout(poll,5000);}
  openView();setTimeout(poll,5000);
})();
