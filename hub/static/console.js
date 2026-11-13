(() => {
  const root = document.getElementById('ap-console');
  if (!root) return;
  const log = document.getElementById('console-log');
  const empty = document.getElementById('console-empty');
  const error = document.getElementById('console-error');
  const kind = document.getElementById('console-kind');
  const search = document.getElementById('console-search');
  const older = document.getElementById('console-older');
  let cursor = 0, first = 0, generation = 0, fetching = false, sending=false, catalogVersion = 0, endpointId, authLost=false;
  const ids = new Set();
  const labels = {connecting:'Verbindung wird aufgebaut',authenticating:'Slot wird angemeldet',connected:'Mit Archipelago verbunden',reconnecting:'Verbindung wird wiederhergestellt',temporarily_unavailable:'Vorübergehend nicht erreichbar',action_required:'Erneutes Verbinden erforderlich',disconnected:'Nicht verbunden',error:'Verbindung fehlgeschlagen'};
  const fail = (text) => { error.textContent = text; error.hidden = !text; };
  async function api(path, form) {
    const response = await fetch(root.dataset.base + path, form ? {method:'POST',body:form,headers:{'X-CSRF-Token':root.dataset.csrf},cache:'no-store'} : {cache:'no-store'});
    const data = await response.json().catch(() => ({error:response.status === 429 ? 'Zu viele Anfragen. Bitte kurz warten.' : 'Die Anfrage konnte nicht verarbeitet werden. Bitte gegebenenfalls erneut anmelden.'}));
    if(response.status===401){authLost=true;window.HUB_AUTH_REQUIRED?.(data.login_url);}
    if (!response.ok) throw new Error(data.error || 'Die Anfrage ist fehlgeschlagen.');
    return data;
  }
  function append(entries, prepend=false) {
    const fragment = document.createDocumentFragment();
    entries.forEach(entry => {
      if (ids.has(entry.id)) return;
      ids.add(entry.id);
      const line = document.createElement('div');
      line.className = 'console-line console-' + entry.kind;
      line.dataset.text = entry.text.toLocaleLowerCase('de');
      const stamp = document.createElement('time');
      stamp.dateTime = new Date(entry.at * 1000).toISOString();
      stamp.textContent = new Date(entry.at * 1000).toLocaleTimeString('de-DE');
      stamp.title = 'Vom Hub aufgezeichnet: ' + new Date(entry.at * 1000).toLocaleString('de-DE');
      const text = document.createElement('span');
      if(entry.delivery){
        const route=document.createElement('span');route.className='console-item-route';
        const sender=document.createElement('strong'),recipient=document.createElement('strong'),item=document.createElement('strong');
        sender.textContent=entry.delivery.sender.name;recipient.textContent=entry.delivery.recipient.name;item.textContent=entry.delivery.item;item.className='console-item-name';
        route.append(sender,document.createTextNode(' → '),recipient,document.createTextNode(': '),item);
        const place=document.createElement('small');place.className='console-item-place';place.textContent=entry.delivery.location.name+' · '+entry.delivery.sender.game;
        text.append(route,place);
      }else text.textContent = entry.text;
      if(entry.visibility==='personal'){
        const privateLabel=document.createElement('small');privateLabel.className='console-private-label';privateLabel.textContent='Nur für dich';text.append(privateLabel);
      }
      line.append(stamp,text);
      line.hidden = !line.dataset.text.includes(search.value.toLocaleLowerCase('de'));
      fragment.append(line);
    });
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 90;
    if (prepend) log.prepend(fragment); else log.append(fragment);
    empty.hidden = ids.size > 0;
    if (!prepend && atBottom) log.scrollTop = log.scrollHeight;
  }
  async function load(previous=false) {
    if (fetching) return;
    const requestGeneration = generation;
    fetching = true;
    try {
      const position = previous && first ? '&before=' + first : cursor ? '&after=' + cursor : '';
      const data = await api('/data?kind=' + encodeURIComponent(kind.value) + position);
      if (requestGeneration !== generation) return;
      const changedCatalog = (catalogVersion !== data.catalog_version || endpointId!==undefined && endpointId!==data.endpoint_id) && cursor > 0;
      catalogVersion = data.catalog_version;
      endpointId=data.endpoint_id;
      if (changedCatalog) {
        cursor=0;first=0;ids.clear();
        log.querySelectorAll('.console-line').forEach(line=>line.remove());
        empty.hidden=false;return;
      }
      const state = document.getElementById('console-state');
      const stateLabel=(labels[data.state] || data.state) + (data.state === 'connected' && data.transport ? ' · ' + data.transport.toUpperCase() : '');
      if(state.textContent!==stateLabel)state.textContent=stateLabel;
      state.className = 'chip ' + (data.state === 'connected' ? 'ok' : ['error','action_required'].includes(data.state) ? 'err' : '');
      const diagnostic=document.getElementById('console-diagnostics');
      if(diagnostic)diagnostic.textContent='Textkonsole: '+(labels[data.state]||data.state)+' · Letzter Kontakt: '+(data.last_contact?new Date(data.last_contact*1000).toLocaleString('de-DE'):'noch keiner')+(data.next_retry_at?' · Nächster Versuch: '+new Date(data.next_retry_at*1000).toLocaleTimeString('de-DE'):'')+' · Lokaler Spielclient: unbekannt';
      const connectLink=document.getElementById('console-connect-link');if(connectLink)connectLink.hidden=data.state==='connected';
      const connectForm=document.getElementById('console-connect'),connectedSlot=document.getElementById('console-connected-slot');
      if(connectForm){
        connectForm.dataset.connected=String(data.state==='connected');
        const slot=connectForm.elements.namedItem('slot');
        if(data.slot&&!slot.dataset.dirty&&[...slot.options].some(o=>o.value===data.slot))slot.value=data.slot;
      }
      if(connectedSlot){connectedSlot.hidden=data.state!=='connected';connectedSlot.textContent='Verbunden als '+(data.slot||'dein Spielslot');}
      document.dispatchEvent(new CustomEvent('hub:console-state',{detail:data}));
      if (data.error) fail(data.error);
      else if (data.state === 'connected') fail('');
      append(data.events,previous);
      if (data.events.length) {
        first = first ? Math.min(first,data.events[0].id) : data.events[0].id;
        if (!previous) cursor = data.cursor;
      }
      if (previous || !position) older.disabled = data.events.length < 100;
    } catch (e) { if (requestGeneration === generation) fail(e.message); }
    finally { fetching = false; }
  }
  async function post(path,form) {
    fail('');
    try { await api(path,form); await load(); return true; }
    catch(e) { fail(e.message); return false; }
  }
  document.getElementById('console-connect')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    form.querySelector('[name=password]').value = '';
    await post('/connect',values);
    values.delete('password');
  });
  document.getElementById('console-disconnect')?.addEventListener('click',() => post('/disconnect',new FormData()));
  document.getElementById('console-connect')?.elements.namedItem('slot')?.addEventListener('change',event=>event.target.dataset.dirty='1');
  document.getElementById('console-command')?.addEventListener('submit',async event => {
    event.preventDefault();
    if(sending)return;
    sending=true;
    const form = event.currentTarget;
    const values = new FormData(form);
    const connect = document.getElementById('console-connect');
    if (connect) {
      const settings = new FormData(connect);
      values.set('slot',settings.get('slot'));
      values.set('transport',settings.get('transport'));
      if (values.get('text') === '/connect') {
        values.set('password',settings.get('password'));
        connect.querySelector('[name=password]').value = '';
      }
    }
    const original=values.get('text');
    const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
    try{if(await post('/command',values)){if(form.elements.namedItem('text').value===original)form.reset();}}
    finally{sending=false;if(submit)submit.disabled=false;}
    values.delete('password');
  });
  kind.addEventListener('change',() => {
    generation++; cursor=0; first=0; ids.clear();
    log.querySelectorAll('.console-line').forEach(line => line.remove());
    empty.hidden=false;
    load();
  });
  search.addEventListener('input',() => log.querySelectorAll('.console-line').forEach(line => {
    line.hidden=!line.dataset.text.includes(search.value.toLocaleLowerCase('de'));
  }));
  older.addEventListener('click',() => load(true));
  // Commands are inserted into the composer. Selection never sends a request.
  const composer=document.getElementById('console-message'),menu=document.getElementById('console-command-menu'),toggle=document.getElementById('console-command-toggle');
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
  async function poll() { if (!authLost && !document.hidden && !root.closest('[data-round-panel]')?.hidden) await load(); setTimeout(poll,2000); }
  poll();
})();
