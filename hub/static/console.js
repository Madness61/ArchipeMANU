(() => {
  const root = document.getElementById('ap-console');
  if (!root) return;
  const log = document.getElementById('console-log');
  const empty = document.getElementById('console-empty');
  const error = document.getElementById('console-error');
  const commandError = document.getElementById('console-command-error');
  const send = document.querySelector('#console-command button[type=submit]');
  const kind = document.getElementById('console-kind');
  const search = document.getElementById('console-search');
  const older = document.getElementById('console-older');
  const archived = root.dataset.archived === '1';
  let cursor = 0, first = 0, generation = 0, fetching = false, sending=false, catalogVersion = 0, endpointId, authLost=false, archiveLoaded=false;
  const ids = new Set();
  const labels = window.HUB_UI.consoleStates;
  let players=new Map(),playerPattern=null,playerSignature='';
  function playerNode(name){
    const player=players.get(name),link=document.createElement(player?'a':'strong');
    link.textContent=name;link.className='console-player-name';link.style.setProperty('--player',window.HUB_UI.playerColor(name));
    if(player){link.href='#'+player.anchor;link.dataset.userId=player.user_id;link.title=player.username;
      link.addEventListener('click',()=>{document.getElementById('console-player-list').open=true;});}
    return link;
  }
  function identify(values=[]){
    const signature=JSON.stringify(values);if(signature===playerSignature)return;playerSignature=signature;
    players=new Map(values.map(p=>[p.slot,p]));
    const names=[...players.keys()].sort((a,b)=>b.length-a.length).map(name=>name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
    playerPattern=names.length?new RegExp('(?<![\\p{L}\\p{N}_])('+names.join('|')+')(?![\\p{L}\\p{N}_])','gu'):null;
    const list=document.getElementById('console-players');
    if(list)list.replaceChildren(...values.map(p=>{const row=document.createElement('li');row.id=p.anchor;
      const name=document.createElement('strong'),account=document.createElement('small');name.textContent=p.slot;
      account.textContent=p.username+' · '+p.game;row.append(name,account);return row;}));
  }
  function messageText(target,content){
    if(!playerPattern){target.textContent=content;return;}
    let offset=0;
    for(const match of content.matchAll(playerPattern)){target.append(document.createTextNode(content.slice(offset,match.index)),playerNode(match[0]));offset=match.index+match[0].length;}
    target.append(document.createTextNode(content.slice(offset)));
  }
  const fail = (text) => { if(error.textContent!==text)error.textContent = text; error.hidden = !text; };
  let lastHubContact=null,hubReachable=null,lastData=null;
  const dateText=seconds=>seconds?new Date(seconds*1000).toLocaleString(window.HUB_I18N.locale):window.HUB_I18N.t('noch keiner');
  function diagnostics(data=lastData){
    const box=document.getElementById('console-diagnostics');if(!box)return;
    const fragment=document.createDocumentFragment();
    const line=(label,value)=>{const row=document.createElement('div'),name=document.createElement('strong'),detail=document.createElement('span');name.textContent=label;detail.textContent=value;row.append(name,detail);fragment.append(row);};
    line(window.HUB_I18N.t('ArchipeMANU-Backend'),hubReachable===false?window.HUB_I18N.t('Nicht erreichbar'):hubReachable?window.HUB_I18N.t('Erreichbar'):window.HUB_I18N.t('Wird geprüft'));
    line(window.HUB_I18N.t('Letzter erfolgreicher Kontakt'),dateText(lastHubContact));
    if(data){
      const web=data.webhost;
      if(web){
        line(window.HUB_I18N.t('Archipelago WebHost-API'),web.state==='not_linked'?window.HUB_I18N.t('Kein Raum verknüpft'):web.error|| (!web.last_success?window.HUB_I18N.t('Noch keine Daten'):web.stale?window.HUB_I18N.t('Veralteter Datenstand'):window.HUB_I18N.t('Aktueller Datenstand')));
        line(window.HUB_I18N.t('Letzter erfolgreicher API-Abruf'),dateText(web.last_success));
        line(window.HUB_I18N.t('Nächste API-Aktualisierung'),web.next_update?dateText(web.next_update):window.HUB_I18N.t('Keine Aktualisierung geplant'));
        const cacheLabels={fresh:window.HUB_I18N.t('Im Cache'),due:window.HUB_I18N.t('Aktualisierung fällig'),updating:window.HUB_I18N.t('Abruf läuft'),error:window.HUB_I18N.t('Abruf fehlgeschlagen')};
        line(window.HUB_I18N.t('API-Cache'),web.endpoints.length?web.endpoints.map(e=>e.endpoint+': '+cacheLabels[e.state]).join(' · '):window.HUB_I18N.t('Noch keine Daten'));
      }
      const room=data.room_connection||data;
      line(window.HUB_I18N.t('Archipelago Live-Konsole'),labels[room.state]||room.state);
      line(window.HUB_I18N.t('Letzter Konsolenkontakt'),dateText(room.last_contact));
      line(window.HUB_I18N.t('Nächster Reconnect-Versuch'),room.next_retry_at?dateText(room.next_retry_at):window.HUB_I18N.t('Keiner geplant'));
      if(data.recording?.last_event)line(window.HUB_I18N.t('Zuletzt aufgezeichnetes Item'),dateText(data.recording.last_event));
      line(window.HUB_I18N.t('Lokaler Spielclient'),window.HUB_I18N.t('Unbekannt · keine zuverlässige technische Prüfung'));
    }
    box.replaceChildren(fragment);
  }
  async function api(path, form) {
    let response;
    try{response = await fetch(root.dataset.base + path, form ? {method:'POST',body:form,headers:{'X-CSRF-Token':root.dataset.csrf},cache:'no-store'} : {cache:'no-store'});}
    catch(error){hubReachable=false;diagnostics();throw new Error(window.HUB_I18N.t('Der Hub ist nicht erreichbar. Der letzte Datenstand bleibt sichtbar.'));}
    hubReachable=true;
    if(response.ok)lastHubContact=Date.now()/1000;
    const data = await response.json().catch(() => ({error:response.status === 429 ? window.HUB_I18N.t('Zu viele Anfragen. Bitte kurz warten.') : window.HUB_I18N.t('Die Anfrage konnte nicht verarbeitet werden. Bitte gegebenenfalls erneut anmelden.')}));
    if(response.status===401){authLost=true;window.HUB_AUTH_REQUIRED?.(data.login_url);}
    if (!response.ok) throw new Error(data.error || window.HUB_I18N.t('Die Anfrage ist fehlgeschlagen.'));
    return data;
  }
  function append(entries, prepend=false) {
    const fragment = document.createDocumentFragment();
    entries.forEach(entry => {
      if (ids.has(entry.id)) return;
      ids.add(entry.id);
      const line = document.createElement('div');
      line.className = 'console-line console-' + entry.kind;
      if(entry.for_me)line.classList.add('console-for-me');
      line.dataset.text = entry.text.toLocaleLowerCase(window.HUB_I18N.locale);
      const stamp = document.createElement('time');
      stamp.dateTime = new Date(entry.at * 1000).toISOString();
      stamp.textContent = new Date(entry.at * 1000).toLocaleTimeString(window.HUB_I18N.locale);
      stamp.title = window.HUB_I18N.t('Vom Hub aufgezeichnet: ') + new Date(entry.at * 1000).toLocaleString(window.HUB_I18N.locale);
      const text = document.createElement('span');
      if(entry.delivery){
        const route=document.createElement('span');route.className='console-item-route';
        const sender=playerNode(entry.delivery.sender.name),recipient=playerNode(entry.delivery.recipient.name),item=document.createElement('strong');
        item.textContent=entry.delivery.item;item.className='console-item-name';
        route.append(sender,document.createTextNode(' → '),recipient,document.createTextNode(': '),item);
        const place=document.createElement('small');place.className='console-item-place';place.textContent=entry.delivery.location.name+' · '+entry.delivery.sender.game;
        text.append(route,place);
      }else messageText(text,entry.text);
      if(entry.source==='received_items'){
        const evidence=document.createElement('small');evidence.className='console-item-place';
        evidence.textContent=window.HUB_I18N.t('Nachträglich bestätigt · Fundzeit unbekannt');
        if(entry.receipt_index!=null)evidence.title=window.HUB_I18N.t('Empfangsreihenfolge für diesen Slot: {v0}',{v0:(entry.receipt_index+1).toLocaleString(window.HUB_I18N.locale)});
        text.append(evidence);
      }
      if(entry.visibility==='personal'){
        const privateLabel=document.createElement('small');privateLabel.className='console-private-label';privateLabel.textContent=window.HUB_I18N.t('Nur für dich')+(entry.actor?' · '+entry.actor.slot:'');text.append(privateLabel);
      }
      line.append(stamp,text);
      line.hidden = !line.dataset.text.includes(search.value.toLocaleLowerCase(window.HUB_I18N.locale));
      fragment.append(line);
    });
    const previousHeight = log.scrollHeight;
    const previousTop = log.scrollTop;
    const atBottom = previousHeight - previousTop - log.clientHeight < 90;
    if (prepend) log.prepend(fragment); else log.append(fragment);
    empty.hidden = ids.size > 0;
    if (prepend) log.scrollTop = previousTop + log.scrollHeight - previousHeight;
    else if (atBottom) log.scrollTop = log.scrollHeight;
  }
  async function load(previous=false) {
    if (fetching) return;
    const requestGeneration = generation;
    fetching = true;
    try {
      const position = previous && first ? '&before=' + first : cursor ? '&after=' + cursor : '';
      const data = await api('/data?kind=' + encodeURIComponent(kind.value) + position);
      if (requestGeneration !== generation) return;
      lastData=data;
      diagnostics(data);
      if(data.recording){
        const recording=data.recording;
        const recordError=document.getElementById('recording-error');if(recordError){recordError.textContent=recording.error;recordError.hidden=!recording.error;}
      }
      const changedCatalog = (catalogVersion !== data.catalog_version || endpointId!==undefined && endpointId!==data.endpoint_id) && cursor > 0;
      catalogVersion = data.catalog_version;
      endpointId=data.endpoint_id;
      const serverRow=document.getElementById('console-server-row');
      const noServer=document.getElementById('console-no-server');
      const autoPort=document.getElementById('console-auto-port');
      const roomSettings=document.getElementById('console-room-settings');
      if(serverRow)serverRow.hidden=!data.server;
      if(noServer)noServer.hidden=!!data.server;
      if(autoPort)autoPort.hidden=!data.server?.auto_port;
      if(roomSettings)roomSettings.hidden=!data.server;
      if(send)send.disabled=sending||!data.server;
      if(data.server){
        const address=data.server.host+':'+data.server.port;
        for(const id of ['console-server-address','host-address']){const node=document.getElementById(id);if(node)node.textContent=address;}
        for(const [id,value] of [['server-host',data.server.host],['server-port',data.server.port]]){const node=document.getElementById(id);if(node)node.textContent=String(value);}
        if(data.server.auto_port)document.querySelectorAll('.hosting-fields input[name=port]').forEach(input=>{
          if(input.value===input.defaultValue){input.value=String(data.server.port);input.defaultValue=input.value;}
        });
      }
      if (changedCatalog) {
        cursor=0;first=0;ids.clear();archiveLoaded=false;
        log.querySelectorAll('.console-line').forEach(line=>line.remove());
        empty.hidden=false;return;
      }
      const state = document.getElementById('console-state');
      const shared=data.room_connection||data;
      identify(data.players);
      const stateLabel=archived ? window.HUB_I18N.t('Protokoll archiviert')
        : !data.server ? window.HUB_I18N.t('Wartet auf Raumverbindung')
        : (labels[shared.state] || shared.state) + (shared.state === 'connected' && shared.transport ? ' · ' + shared.transport.toUpperCase() : '');
      if(state.textContent!==stateLabel)state.textContent=stateLabel;
      state.className = 'chip ' + (shared.state === 'connected' ? 'ok' : ['error','action_required'].includes(shared.state) ? 'err' : '');
      document.dispatchEvent(new CustomEvent('hub:console-state',{detail:data}));
      fail(archived ? '' : shared.error || '');
      append(data.events,previous);
      if (data.events.length) {
        first = first ? Math.min(first,data.events[0].id) : data.events[0].id;
        if (!previous) cursor = data.cursor;
      }
      if (previous || !position) older.disabled = data.events.length < 100;
      if (archived) archiveLoaded = true;
    } catch (e) { if (requestGeneration === generation) fail(e.message); }
    finally { fetching = false; }
  }
  async function post(path,form,showError=fail) {
    showError('');
    try { await api(path,form); await load(); return true; }
    catch(e) { showError(e.message); return false; }
  }
  document.getElementById('recording-start')?.addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,values=new FormData(form),button=form.querySelector('button[type=submit]');
    form.elements.password.value='';button.disabled=true;
    const indicator=document.getElementById('console-state');indicator.textContent=labels.connecting;indicator.className='chip warn';
    try{await post('/recording/start',values);}finally{values.delete('password');button.disabled=false;}
  });
  document.getElementById('console-command')?.addEventListener('submit',async event => {
    event.preventDefault();
    if(sending)return;
    sending=true;
    const form = event.currentTarget;
    const values = new FormData(form);
    const original=values.get('text');
    const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
    const showError=text=>{commandError.textContent=text;commandError.hidden=!text;};
    try{if(await post('/command',values,showError)){if(form.elements.namedItem('text').value===original){form.elements.namedItem('text').value='';try{sessionStorage.removeItem(draftKey);}catch{}}}}
    finally{sending=false;if(submit)submit.disabled=!lastData?.server;}
  });
  kind.addEventListener('change',() => {
    generation++; cursor=0; first=0; ids.clear(); archiveLoaded=false;
    log.querySelectorAll('.console-line').forEach(line => line.remove());
    empty.hidden=false;
    load();
  });
  search.addEventListener('input',() => log.querySelectorAll('.console-line').forEach(line => {
    line.hidden=!line.dataset.text.includes(search.value.toLocaleLowerCase(window.HUB_I18N.locale));
  }));
  older.addEventListener('click',() => load(true));
  // Commands are inserted into the composer. Selection never sends a request.
  const composer=document.getElementById('console-message'),menu=document.getElementById('console-command-menu'),toggle=document.getElementById('console-command-toggle');
  const draftKey='hub.console.draft.v1:'+root.dataset.user+':'+root.dataset.base;
  if(composer){try{if(!composer.value)composer.value=sessionStorage.getItem(draftKey)||'';}catch{}composer.addEventListener('input',()=>{try{sessionStorage.setItem(draftKey,composer.value);}catch{}});}
  const choices=menu?[...menu.querySelectorAll('[data-insert-command]')]:[];
  const showCommands=open=>{if(!menu)return;menu.hidden=!open;toggle.setAttribute('aria-expanded',String(open));};
  const filterCommands=()=>{
    if(!composer)return;
    const query=composer.value.trim().toLowerCase();
    const isCommand=query.startsWith('/')||query.startsWith('!');
    choices.forEach(button=>button.hidden=isCommand&&!button.dataset.insertCommand.trim().startsWith(query));
    showCommands(isCommand&&!query.includes(' ')&&choices.some(b=>!b.hidden)&&!choices.some(b=>b.dataset.insertCommand.trim()===query));
  };
  composer?.addEventListener('input',filterCommands);
  composer?.addEventListener('keydown',event=>{
    if(event.key==='Escape'){showCommands(false);return;}
    if(event.key==='ArrowDown'&&menu&&!menu.hidden){event.preventDefault();choices.find(b=>!b.hidden)?.focus();}
  });
  toggle?.addEventListener('click',()=>{if(menu.hidden){choices.forEach(b=>b.hidden=false);showCommands(true);choices[0]?.focus();}else{showCommands(false);composer.focus();}});
  choices.forEach(button=>{
    button.addEventListener('click',()=>{composer.value=button.dataset.insertCommand;showCommands(false);composer.focus();composer.setSelectionRange(composer.value.length,composer.value.length);});
    button.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();showCommands(false);composer.focus();}
      if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
        event.preventDefault();const visible=choices.filter(b=>!b.hidden),i=visible.indexOf(button);
        visible[event.key==='Home'?0:event.key==='End'?visible.length-1:(i+(event.key==='ArrowDown'?1:-1)+visible.length)%visible.length]?.focus();
      }
    });
  });
  document.getElementById('console-command')?.addEventListener('submit',()=>showCommands(false));
  async function poll() { if (!authLost && !archiveLoaded && !document.hidden && !root.closest('[data-round-panel]')?.hidden) await load(); setTimeout(poll,2000); }
  poll();
})();
