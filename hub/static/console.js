(() => {
  const root = document.getElementById('ap-console');
  if (!root) return;
  const log = document.getElementById('console-log');
  const empty = document.getElementById('console-empty');
  const error = document.getElementById('console-error');
  const kind = document.getElementById('console-kind');
  const search = document.getElementById('console-search');
  const older = document.getElementById('console-older');
  let cursor = 0, first = 0, generation = 0, fetching = false, catalogVersion = 0;
  const ids = new Set();
  const labels = {connecting:'Verbindung wird aufgebaut',authenticating:'Slot wird angemeldet',connected:'Mit Archipelago verbunden',disconnected:'Nicht verbunden',error:'Verbindung fehlgeschlagen'};
  const fail = (text) => { error.textContent = text; error.hidden = !text; };
  async function api(path, form) {
    const response = await fetch(root.dataset.base + path, form ? {method:'POST',body:form,headers:{'X-CSRF-Token':root.dataset.csrf},cache:'no-store'} : {cache:'no-store'});
    const data = await response.json().catch(() => ({error:response.status === 429 ? 'Zu viele Anfragen. Bitte kurz warten.' : 'Die Anfrage konnte nicht verarbeitet werden. Bitte gegebenenfalls erneut anmelden.'}));
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
      text.textContent = entry.text;
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
      const changedCatalog = catalogVersion !== data.catalog_version && cursor > 0;
      catalogVersion = data.catalog_version;
      if (changedCatalog) {
        cursor=0;first=0;ids.clear();
        log.querySelectorAll('.console-line').forEach(line=>line.remove());
        empty.hidden=false;return;
      }
      const state = document.getElementById('console-state');
      state.textContent = (labels[data.state] || data.state) + (data.state === 'connected' && data.transport ? ' · ' + data.transport.toUpperCase() : '');
      state.className = 'chip ' + (data.state === 'connected' ? 'ok' : data.state === 'error' ? 'err' : '');
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
  document.getElementById('console-command')?.addEventListener('submit',async event => {
    event.preventDefault();
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
    if (await post('/command',values)) form.reset();
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
  async function poll() { if (!document.hidden) await load(); setTimeout(poll,2000); }
  poll();
})();
