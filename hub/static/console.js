(() => {
  const root = document.getElementById('ap-console');
  if (!root) return;
  const openPopout = document.getElementById('console-open-popout');
  const compact = document.body.classList.contains('console-popout');
  let popoutWindow, openingPopout = false, useBrowserWindow = false;
  function openBrowserWindow(url) {
    const popup = window.open('', '_blank', 'popup,width=360,height=550,resizable=yes');
    if (popup) {
      popup.opener = null;
      popup.location.replace(url);
      popoutWindow = popup;
    }
    return popup;
  }
  openPopout?.addEventListener('click', async event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (popoutWindow && !popoutWindow.closed) {
      event.preventDefault();
      popoutWindow.focus();
      return;
    }
    if (useBrowserWindow || !window.documentPictureInPicture) {
      if (openBrowserWindow(openPopout.href)) {
        event.preventDefault();
        document.getElementById('console-popout-error').hidden = true;
      }
      return;
    }
    event.preventDefault();
    if (openingPopout) return;
    openingPopout = true;
    try {
      popoutWindow = await window.documentPictureInPicture.requestWindow({width:360, height:550});
      const doc = popoutWindow.document;
      const frame = doc.createElement('iframe');
      frame.title = doc.title = window.HUB_I18N.t('Archipelago Live-Konsole');
      frame.src = openPopout.href;
      frame.style.cssText = 'display:block;width:100%;height:100vh;border:0';
      doc.body.style.margin = '0';
      doc.body.append(frame);
    } catch {
      popoutWindow?.close();
      useBrowserWindow = true;
      document.getElementById('console-popout-error').hidden = !!openBrowserWindow(openPopout.href);
    } finally {
      openingPopout = false;
    }
  });
  const log = document.getElementById('console-log');
  const empty = document.getElementById('console-empty');
  const error = document.getElementById('console-error');
  const commandError = document.getElementById('console-command-error');
  const send = document.querySelector('#console-command button[type=submit]');
  const kind = document.getElementById('console-kind');
  const search = document.getElementById('console-search');
  const older = document.getElementById('console-older');
  const archived = root.dataset.archived === '1';
  const nearBottom = () => log.scrollHeight - log.scrollTop - log.clientHeight < (compact ? 40 : 90);
  if (compact) {
    let following = true;
    log.addEventListener('scroll', () => { following = nearBottom(); });
    new ResizeObserver(() => {
      if (following) log.scrollTop = log.scrollHeight;
    }).observe(log);
  }
  let cursor = 0, first = 0, generation = 0, fetching = false, sending=false, catalogVersion = 0, endpointId, authLost=false, archiveLoaded=false;
  let historyLoaded = false;
  const ids = new Set();
  const labels = window.HUB_UI.consoleStates;
  const retrying = room => room.state === 'reconnecting' || room.state === 'temporarily_unavailable';
  const startingRoom = data => data?.room_connection?.state !== 'connected'
    && ['checking','starting'].includes(data?.room_start?.state);
  let players=new Map(),playerPattern=null,playerSignature='';
  function playerNode(name){
    const player=compact?null:players.get(name),link=document.createElement(player?'a':'strong');
    link.textContent=name;link.className='console-player-name';link.style.setProperty('--player',window.HUB_UI.playerColor(name));
    if(player){
      const roundPlayer = document.getElementById(player.anchor.replace('console-', 'round-'));
      link.href='#'+(roundPlayer?.id||player.anchor);link.dataset.userId=player.user_id;link.title=player.username;
      if(!roundPlayer)link.addEventListener('click',()=>{document.getElementById('console-player-list').open=true;});
    }
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
  function revokePopout() {
    authLost = true;
    log.replaceChildren();
    if (send) document.getElementById('console-compose').hidden = true;
    older.disabled = true;
    kind.disabled = true;
    const state = document.getElementById('console-state');
    state.textContent = labels.disconnected;
    state.className = 'chip';
  }
  let lastHubContact=null,hubReachable=null,lastData=null;
  const dateText=seconds=>seconds?new Date(seconds*1000).toLocaleString(window.HUB_I18N.locale):window.HUB_I18N.t('noch keiner');
  function diagnostics(data=lastData){
    const box=document.getElementById('console-diagnostics');if(!box)return;
    const fragment=document.createDocumentFragment();
    const line=(label,value)=>{const row=document.createElement('div'),name=document.createElement('strong'),detail=document.createElement('span');name.textContent=label;detail.textContent=value;row.append(name,detail);fragment.append(row);};
    if(data){
      const room=data.room_connection||data;
      line(window.HUB_I18N.t('Archipelago Live-Konsole'),labels[room.state]||room.state);
      if(data.recording?.automatic && room.slot)line(window.HUB_I18N.t('AP-Slot des Hintergrundlesers'),room.slot);
      line(window.HUB_I18N.t('Letzter Konsolenkontakt'),dateText(room.last_contact));
      line(window.HUB_I18N.t('Nächster Reconnect-Versuch'),room.next_retry_at?dateText(room.next_retry_at):window.HUB_I18N.t('Keiner geplant'));
      if(room.retry_attempt)line(window.HUB_I18N.t('Verbindungsversuche'),room.retry_attempt.toLocaleString(window.HUB_I18N.locale));
      if(room.error)line(window.HUB_I18N.t('Letzter Verbindungsfehler'),room.error);
      if(data.recording?.last_event)line(window.HUB_I18N.t('Zuletzt aufgezeichnetes Item'),dateText(data.recording.last_event));
    }
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
    if (!response.ok) {
      const message = data.error ? window.HUB_I18N.t(data.error) : window.HUB_I18N.t('Die Anfrage ist fehlgeschlagen.');
      if (compact && (response.status === 401 || !form && [403,404,409].includes(response.status))) {
        revokePopout();
        fail(message);
      }
      throw new Error(message);
    }
    return data;
  }
  function append(entries, prepend=false, live=false) {
    const fragment = document.createDocumentFragment();
    entries.forEach(entry => {
      if (ids.has(entry.id)) return;
      ids.add(entry.id);
      const line = document.createElement('div');
      line.className = 'console-line console-' + entry.kind;
      if(compact){
        if(live && entry.source === 'live' && (entry.for_me || entry.from_me)) line.classList.add('console-own-live');
      }else if(entry.for_me)line.classList.add('console-for-me');
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
      }else if(entry.connection_role==='reader' || entry.connection_role==='text_client'){
        text.textContent=entry.text;
        text.title=entry.server_text;
        text.className='muted';
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
      if(search)line.hidden = !line.dataset.text.includes(search.value.toLocaleLowerCase(window.HUB_I18N.locale));
      fragment.append(line);
    });
    const previousHeight = log.scrollHeight;
    const previousTop = log.scrollTop;
    const atBottom = nearBottom();
    if (prepend) log.prepend(fragment); else log.append(fragment);
    empty.hidden = ids.size > 0;
    if (prepend) log.scrollTop = previousTop + log.scrollHeight - previousHeight;
    else if (atBottom) log.scrollTop = log.scrollHeight;
  }
  async function load(previous=false) {
    if (fetching || authLost) return;
    const requestGeneration = generation;
    fetching = true;
    try {
      const position = previous && first ? '&before=' + first : cursor ? '&after=' + cursor : '';
      const data = await api('/data?kind=' + encodeURIComponent(kind.value) + position);
      if (requestGeneration !== generation || authLost) return;
      if (compact && String(data.viewer_id) !== root.dataset.user) {
        revokePopout();
        throw new Error(window.HUB_I18N.t('Dieses Popout gehört zu einer anderen Anmeldung. Öffne es erneut.'));
      }
      lastData=data;
      diagnostics(data);
      if(data.recording){
        const recording=data.recording;
        const recordError=document.getElementById('recording-error');
        if(recordError){
          const warning=recording.console_state==='action_required' ? recording.error : '';
          if(recordError.textContent!==warning)recordError.textContent=warning;
          recordError.hidden=!warning;
        }
      }
      const changedCatalog = historyLoaded && (catalogVersion !== data.catalog_version || endpointId !== data.endpoint_id);
      catalogVersion = data.catalog_version;
      endpointId=data.endpoint_id;
      const serverRow=document.getElementById('console-server-row');
      const noServer=document.getElementById('console-no-server');
      const autoPort=document.getElementById('console-auto-port');
      const roomSettings=document.getElementById('console-room-settings');
      if(serverRow)serverRow.hidden=!data.server || startingRoom(data) && data.server.auto_port;
      if(noServer)noServer.hidden=!!data.server || startingRoom(data);
      if(autoPort)autoPort.hidden=!data.server?.auto_port;
      if(roomSettings)roomSettings.hidden=!data.server;
      if(send)send.disabled=sending||!data.server||startingRoom(data);
      if(data.server){
        const address=data.server.host+':'+data.server.port;
        for(const id of ['console-server-address','host-address']){const node=document.getElementById(id);if(node)node.textContent=address;}
        for(const [id,value] of [['server-host',data.server.host],['server-port',data.server.port]]){const node=document.getElementById(id);if(node)node.textContent=String(value);}
        if(data.server.auto_port)document.querySelectorAll('.hosting-fields input[name=port]').forEach(input=>{
          if(input.value===input.defaultValue){input.value=String(data.server.port);input.defaultValue=input.value;}
        });
      }
      if (changedCatalog) {
        cursor=0;first=0;ids.clear();archiveLoaded=false;historyLoaded=false;
        log.querySelectorAll('.console-line').forEach(line=>line.remove());
        empty.hidden=false;return;
      }
      const state = document.getElementById('console-state');
      const shared=data.room_connection||data;
      const launch=data.room_start;
      const showLaunch=shared.state!=='connected' && (['checking','starting','error'].includes(launch?.state)
        || (launch?.state==='reachable' && ['connecting','disconnected','not_started'].includes(shared.state)));
      identify(data.players);
      const stateLabel=archived ? window.HUB_I18N.t('Protokoll archiviert')
        : showLaunch ? window.HUB_UI.roomStartLabel(launch)
        : !data.server ? window.HUB_I18N.t('Wartet auf Raumverbindung')
        : (labels[shared.state] || shared.state) + (shared.state === 'connected' && shared.transport ? ' · ' + shared.transport.toUpperCase() : '');
      if(state.textContent!==stateLabel)state.textContent=stateLabel;
      state.className = 'chip ' + (shared.state === 'connected' || showLaunch && launch.state==='reachable'
        ? 'ok' : showLaunch && launch.state==='error' || ['error','action_required'].includes(shared.state) ? 'err' : '');
      document.dispatchEvent(new CustomEvent('hub:console-state',{detail:data}));
      fail(archived ? '' : showLaunch ? launch.error || '' : retrying(shared) ? '' : shared.error || '');
      append(data.events,previous,historyLoaded && !previous);
      historyLoaded = true;
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
    finally{sending=false;if(submit)submit.disabled=!lastData?.server||startingRoom(lastData);}
  });
  kind.addEventListener('change',() => {
    generation++; cursor=0; first=0; ids.clear(); archiveLoaded=false; historyLoaded=false;
    log.querySelectorAll('.console-line').forEach(line => line.remove());
    empty.hidden=false;
    load();
  });
  search?.addEventListener('input',() => log.querySelectorAll('.console-line').forEach(line => {
    line.hidden=!line.dataset.text.includes(search.value.toLocaleLowerCase(window.HUB_I18N.locale));
  }));
  older.addEventListener('click',() => load(true));
  // Commands are inserted into the composer. Selection never sends a request.
  const composer=document.getElementById('console-message'),menu=document.getElementById('console-command-menu'),toggle=document.getElementById('console-command-toggle');
  const draftKey='hub.console.draft.v1:'+root.dataset.user+':'+root.dataset.base+(compact?':popout':'');
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
