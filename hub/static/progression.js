/* Optional spoiler-gated help. Opening a panel never starts a logic worker. */
(() => {
  const root=document.getElementById('progression-panel');
  if(!root)return;
  const t=window.HUB_I18N.t, $=id=>document.getElementById(id);
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const labels={
    checked:t('Bereits eingesammelt'),unchecked:t('Noch nicht eingesammelt'),unknown:t('Unbekannter Status'),
    received:t('Empfang bestätigt'),not_received:t('Zu diesem Stand noch nicht empfangen'),
    progression:t('Progression'),useful:t('Useful'),filler:t('Filler'),trap:t('Trap')
  };
  const inlineStatus={
    checked:t('Gefunden'),unchecked:t('Offen'),unknown:t('Fundstatus unbekannt')
  };
  const reasons={
    busy:t('Archipelago wird gerade verwendet. Bitte die Analyse später erneut starten.'),
    historical_seed:t('Für diesen älteren Seed fehlen die Rekonstruktionsdaten. Die Itemsuche bleibt verfügbar.'),
    placements_missing:t('Für diesen Seed sind keine vollständigen, verifizierten Itemplatzierungen gespeichert.'),
    inventory_missing:t('Ein vollständiger, aktueller Itemzustand fehlt. Nutze /received in der Konsole oder warte auf den verknüpften Tracker.'),
    runtime_changed:t('Die installierte Archipelago- oder APWorld-Version passt nicht zum Seed. Die Itemsuche bleibt verfügbar.'),
    yaml_changed:t('Die ursprünglichen Spieler-YAMLs fehlen oder stimmen nicht mehr mit dem Seed überein.'),
    reconstruction_mismatch:t('Die rekonstruierte Welt stimmt nicht vollständig mit dem erzeugten Seed überein. Es werden keine Logikergebnisse angezeigt.'),
    item_links:t('Item-Link-Gruppen können noch nicht zuverlässig dynamisch ausgewertet werden. Nutze die statische Analyse und Itemsuche.'),
    incomplete_checks:t('Die gemeldeten Checks passen nicht vollständig zur rekonstruierten Welt.'),
    incomplete_start_inventory:t('Das Startinventar ist noch nicht vollständig vom Server bestätigt.'),
    unmatched_synthetic_item:t('Ein zusätzliches Start- oder Serveritem lässt sich nicht eindeutig dem Seed zuordnen.'),
    unmatched_receipt:t('Ein empfangenes Item lässt sich nicht eindeutig dem Seed zuordnen.'),
    timeout:t('Die Berechnung hat ihr Zeitlimit erreicht. Konsole und Itemsuche bleiben verfügbar.'),
    worker_failed:t('Diese Spielwelt konnte nicht zuverlässig ausgewertet werden. Konsole und Itemsuche bleiben verfügbar.')
  };
  let revealed=root.dataset.revealed==='1',view='finder',page=1,pages=1,sequence=0,analysisBusy=false,timer=null;
  const fail=text=>{$('progression-error').textContent=text;$('progression-error').hidden=!text;};
  async function api(path,body){
    const response=await fetch(root.dataset.base+path,{cache:'no-store',...(body?{method:'POST',headers:{'X-CSRF-Token':root.dataset.csrf},body:new URLSearchParams(body)}:{})});
    const data=await response.json();
    if(response.status===401)window.HUB_AUTH_REQUIRED?.(data.login_url);
    if(!response.ok){const error=Error(data.error||t('Die Anfrage konnte nicht abgeschlossen werden.'));error.status=response.status;throw error;}
    return data;
  }
  function selectTab(value){
    view=value;
    root.querySelectorAll('[data-progression-section]').forEach(n=>n.hidden=n.dataset.progressionSection!==view);
    root.querySelectorAll('[data-progression-tab]').forEach(n=>{if(n.dataset.progressionTab===view)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});
    if(revealed){if(view==='finder')find();else analysis(false);}
  }
  function consent(value){
    const changed=revealed!==value;
    revealed=value;$('progression-consent').hidden=value;$('progression-content').hidden=!value;
    if($('live-item-consent'))$('live-item-consent').hidden=value||!$('live-item-query').value.trim()||root.open;
    if(!value&&$('live-item-output')){$('live-item-output').hidden=true;$('live-item-results').replaceChildren();}
    if(!value){clearTimeout(timer);$('progression-results').replaceChildren();$('progression-helpful').replaceChildren();$('progression-goals').replaceChildren();$('progression-reachable').replaceChildren();$('progression-spheres').replaceChildren();}
    if(changed)document.dispatchEvent(new Event('hub:progression-consent'));
  }
  async function open(value){
    if($('live-item-consent'))$('live-item-consent').hidden=true;
    fail('');if(!root.open)root.showModal();
    try{const state=await api('/state');$('progression-support').textContent=state.support==='partial'?t('Teilweise Unterstützung'):t('Basisunterstützung');consent(state.revealed);selectTab(value);}
    catch(error){fail(error.message);}
  }
  document.querySelectorAll('[data-progression-open]').forEach(button=>button.addEventListener('click',()=>{
    if(button.hasAttribute('data-round-analysis')){
      for(const id of ['progression-analyze','progression-goal-analyze']){
        const select=$(id)?.elements.slot;
        const selected=$('round-player-detail').dataset.slot;
        if(select && [...select.options].some(option=>option.value===selected)){
          select.value=selected;
          if (id==='progression-analyze') $('progression-target')?.replaceChildren(new Option(t('Allgemeine Hilfe'),''));
        }
      }
    }
    open(button.dataset.progressionOpen);
  }));
  root.querySelectorAll('[data-progression-tab]').forEach(button=>button.addEventListener('click',()=>selectTab(button.dataset.progressionTab)));
  $('progression-close').addEventListener('click',()=>root.close());
  root.addEventListener('close',()=>{
    clearTimeout(timer);sequence++;consent(revealed);
    document.dispatchEvent(new Event('hub:progression-closed'));
  });
  $('progression-reveal').addEventListener('click',async()=>{try{const state=await api('/consent',{reveal:'1'});consent(state.revealed);selectTab(view);}catch(error){fail(error.message);}});
  $('progression-hide').addEventListener('click',async()=>{try{await api('/consent',{reveal:'0'});sequence++;consent(false);}catch(error){fail(error.message);}});
  function observation(at){return at?new Date(at*1000).toLocaleString(window.HUB_I18N.locale):t('Unbekannter Status');}
  function placement(row){
    const card=node('article',null,'progression-item');
    card.append(node('h4',row.item),node('span',labels[row.category]||row.category,'chip'));
    const recipient=node('p',t('Empfänger')+': '+row.recipient_player.name+' · '+row.recipient_player.game);
    recipient.dataset.playerName=row.recipient_player.name;recipient.style.setProperty('--player',window.HUB_UI.playerColor(row.recipient_player.name));
    card.append(recipient,node('p',t('Finder / Welt')+': '+row.finder_player.name+' · '+row.finder_player.game),
      node('p',t('Fundort')+': '+row.location),node('p',t('Fundort-Check')+': '+labels[row.check_status]),
      node('p',t('Itemempfang')+': '+labels[row.receipt_status]));
    if(row.check_at)card.append(node('p',t('Check-Stand')+': '+observation(row.check_at),'small muted'));
    if(row.receipt_at)card.append(node('p',t('Empfangsstand')+': '+observation(row.receipt_at),'small muted'));
    return card;
  }
  // Compact live search reuses the same evidence, consent and endpoint as the
  // detailed finder. No progression worker is created by searching.
  const inlineForm=$('live-item-search');
  let inlinePage=1,inlineSequence=0,inlineTimer=null,inlineEvidence='',inlineBusy=false;
  const inlineFail=text=>{if($('live-item-error')){$('live-item-error').textContent=text;$('live-item-error').hidden=!text;}};
  async function inlineFind(){
    if(!inlineForm)return;
    const query=$('live-item-query').value.trim(),current=++inlineSequence;
    if(!query){$('live-item-output').hidden=true;$('live-item-results').replaceChildren();return;}
    inlineFail('');
    if(!revealed){consent(false);return;}
    inlineBusy=true;
    try{
      const data=await api('/items?'+new URLSearchParams({q:query,page:inlinePage,limit:5}));
      if(current!==inlineSequence||!revealed)return;
      inlinePage=data.page;
      $('live-item-results').replaceChildren(...data.rows.map(row=>{
        const card=node('article',null,'live-item-result');
        const heading=node('div',null,'row spread');
        heading.append(node('h4',row.item),node('span',inlineStatus[row.check_status],
          'chip '+(row.check_status==='checked'?'ok':'')));
        card.append(heading,
          node('p',t('Empfänger')+': '+row.recipient_player.name,'small'),
          node('p',row.location+' · '+row.finder_player.name+' ('+row.finder_player.game+')','small'));
        if(row.receipt_status==='received')card.append(node('p',labels.received,'small muted'));
        return card;
      }));
      $('live-item-output').hidden=false;
      $('live-item-count').textContent=data.available?t('{v0} Treffer',{v0:data.total.toLocaleString(window.HUB_I18N.locale)}):reasons.placements_missing;
      $('live-item-previous').hidden=$('live-item-next').hidden=data.pages<=1;
      $('live-item-previous').disabled=inlinePage<=1;$('live-item-next').disabled=inlinePage>=(data.pages||1);
    }catch(error){if(current===inlineSequence){if(error.status===403)consent(false);inlineFail(error.message);}}
    finally{if(current===inlineSequence)inlineBusy=false;}
  }
  if(inlineForm){
    inlineForm.addEventListener('submit',event=>{event.preventDefault();clearTimeout(inlineTimer);inlinePage=1;inlineFind();});
    $('live-item-query').addEventListener('input',()=>{clearTimeout(inlineTimer);inlineSequence++;inlineBusy=false;inlinePage=1;
      $('live-item-output').hidden=true;
      if(!$('live-item-query').value.trim()){$('live-item-results').replaceChildren();$('live-item-consent').hidden=true;inlineFail('');}
      else if(revealed)inlineTimer=setTimeout(inlineFind,350);
    });
    $('live-item-reveal').addEventListener('click',async()=>{try{const state=await api('/consent',{reveal:'1'});consent(state.revealed);inlinePage=1;inlineFind();}catch(error){inlineFail(error.message);}});
    $('live-item-hide').addEventListener('click',async()=>{try{await api('/consent',{reveal:'0'});inlineSequence++;consent(false);}catch(error){inlineFail(error.message);}});
    $('live-item-previous').addEventListener('click',()=>{inlinePage--;inlineFind();});
    $('live-item-next').addEventListener('click',()=>{inlinePage++;inlineFind();});
    document.addEventListener('hub:console-state',event=>{
      const evidence=JSON.stringify([event.detail.recording?.last_event,event.detail.webhost?.last_success]);
      if(evidence===inlineEvidence)return;inlineEvidence=evidence;
      if(revealed&&!inlineBusy&&$('live-item-query').value.trim())inlineFind();
    });
  }
  const playerForm = $('round-item-filters');
  if (playerForm) {
    const panel = $('round-player-items');
    const sheet = $('round-player-detail');
    const tools = $('round-item-tools');
    const views = [...tools.querySelectorAll('[data-round-item-view]')];
    const results = $('round-item-list');
    const message = $('round-item-result-status');
    const spoiler = $('round-item-spoilers');
    const pagination = $('round-item-pagination');
    const previous = $('round-item-previous');
    const next = $('round-item-next');
    const suggestion = $('round-analysis-suggestion');
    const context = $('round-analysis-context');
    const analysisButton = $('round-analysis-open');
    const {locale} = window.HUB_I18N;
    const number = new Intl.NumberFormat(locale);
    const list = new Intl.ListFormat(locale);
    const date = new Intl.DateTimeFormat(locale, {dateStyle: 'short', timeStyle: 'short'});
    const pageSize = 10;
    const players = new Map([...document.querySelectorAll('[data-round-player]')].map(choice => [choice.dataset.roundPlayer, choice.id]));
    const states = {
      found: t('Gefunden · Empfang offen'), unchecked: t('Check noch offen'),
      unreceived: t('Noch nicht erhalten'), received: t('Empfang bestätigt'),
      unknown: t('Fund und Empfang unbekannt')
    };
    const receiptLabels = {
      received: t('Empfang bestätigt'), not_received: t('Zu diesem Stand noch nicht empfangen'),
      unknown: t('Empfang unbekannt')
    };
    const empty = {
      open: t('Keine offenen Progression-Items bestätigt.'),
      received: t('Noch kein Empfang eines Progression-Items bestätigt.'),
      unknown: t('Für alle Progression-Items liegt ein bestätigter Fund- oder Empfangsstand vor.'),
      help: t('Keine offenen Progression-Items für andere Spieler in dieser Welt.')
    };
    let focus = 'open', playerPage = 1, chooseInitialView = true, version = '', itemKey = '', queryTimer;
    let itemRequest = 0, overviewRequest = 0, overviewTimer, expires = Infinity, moveToResults = false;
    let overviewState;
    const visible = () => !panel.closest('[data-round-panel]').hidden && !document.hidden;

    function formatFinders(finders) {
      return finders.length <= 3 ? list.format(finders)
        : t('{v0} und {v1} weitere', {v0: finders.slice(0, 2).join(', '), v1: number.format(finders.length - 2)});
    }

    function itemRow(group, expanded) {
      const row = node('li', null, 'round-item');
      row.dataset.item = JSON.stringify([group.recipient, group.name]);
      const heading = node('div', null, 'round-item-main');
      heading.append(node('strong', group.name + (group.total > 1 ? ' × ' + number.format(group.total) : '')));
      const counts = node('div', null, 'row round-item-counts');
      for (const [state, label] of Object.entries(states)) {
        const count = group.states[state];
        if (count) counts.append(node('span', group.total > 1 ? number.format(count) + ' · ' + label : label, state));
      }
      heading.append(counts);
      row.append(heading);
      if (focus === 'help') {
        const label = t('Für {v0}', {v0: group.recipient});
        const recipient = node('p', null, 'muted round-item-source');
        if (players.has(group.recipient)) {
          const link = node('a', label);
          link.href = '#' + players.get(group.recipient);
          recipient.append(link);
        } else {
          recipient.textContent = label;
        }
        row.append(recipient);
      }
      if (group.effect) row.append(node('p', t('Ein Exemplar könnte +{v0} Checks und +{v1} Bereiche öffnen.',
        {v0: number.format(group.effect.checks), v1: number.format(group.effect.regions)}), 'muted round-item-source'));
      if (group.copies?.length) {
        if (focus !== 'help') {
          const finders = [...new Set(group.copies.map(copy => copy.finder))];
          row.append(node('p', t('In der Welt von {v0}', {v0: formatFinders(finders)}), 'muted round-item-source'));
        }
        const locations = node('details');
        locations.open = expanded;
        locations.append(node('summary', t('Fundorte')));
        function showCopies() {
          if (!locations.open || locations.querySelector('ul')) return;
          const copies = node('ul');
          for (const copy of group.copies) {
            const item = node('li');
            const status = [inlineStatus[copy.check_status], receiptLabels[copy.status]];
            const detail = node('small');
            if (focus !== 'help' && players.has(copy.finder)) {
              const link = node('a', copy.finder);
              link.href = '#' + players.get(copy.finder);
              detail.append(link, ' · ');
            }
            detail.append(status.join(' · '));
            if (copy.at) detail.title = t('Datenstand {v0}', {v0: date.format(copy.at * 1000)});
            item.append(node('strong', copy.location), detail);
            copies.append(item);
          }
          locations.append(copies);
        }
        locations.addEventListener('toggle', showCopies);
        showCopies();
        row.append(locations);
      }
      return row;
    }

    function setFocus(value) {
      focus = value;
      playerPage = 1;
      views.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.roundItemView === value)));
    }

    function clearItems() {
      moveToResults = false;
      results.replaceChildren();
      pagination.hidden = true;
      message.textContent = t('Progression-Items werden geladen …');
    }

    async function loadPlayerItems() {
      if (!visible() || !sheet.dataset.slot) return;
      const query = playerForm.elements.q.value.trim();
      const params = new URLSearchParams({recipient: sheet.dataset.slot, focus, q: query, page: playerPage, limit: pageSize});
      const key = JSON.stringify([params.toString(), revealed, version]);
      if (key === itemKey) return;
      itemKey = key;
      const request = ++itemRequest;
      try {
        const data = await api('/items?' + params);
        if (request !== itemRequest) return;
        if (revealed !== data.revealed) {
          consent(data.revealed);
          return;
        }
        if (chooseInitialView) {
          chooseInitialView = false;
          const initial = ['open', 'unknown', 'received', 'help'].find(value => data.counts[value] > 0);
          if (initial && initial !== focus) {
            setFocus(initial);
            loadPlayerItems();
            return;
          }
        }
        const expanded = new Set([...results.querySelectorAll('details[open]')].map(detail => detail.closest('li').dataset.item));
        const focused = document.activeElement.closest?.('.round-item')?.dataset.item;
        results.replaceChildren(...data.rows.map(group => itemRow(group, expanded.has(JSON.stringify([group.recipient, group.name])))));
        if (focused) [...results.children].find(row => row.dataset.item === focused)?.querySelector('summary')?.focus({preventScroll:true});
        for (const button of views) {
          const view = button.dataset.roundItemView;
          const count = view === 'useful' ? data.helpful : data.counts[view];
          button.firstElementChild.textContent = count == null || (view === 'useful' && focus !== view) ? '' : number.format(count);
          if (view === 'help') button.hidden = !revealed || (!count && focus !== view);
          if (view === 'useful') button.hidden = !revealed || !sheet.dataset.own;
        }
        playerPage = data.page;
        const hasItems = Object.values(data.counts).some(Boolean);
        message.textContent = !data.available ? reasons.placements_missing : !hasItems ? t('Keine Progression-Items für diesen Slot gespeichert.')
          : data.total ? '' : query ? t('Keine passenden Progression-Items.')
          : focus !== 'useful' ? empty[focus]
          : data.analysis_state === 'ready' ? t('Die geprüften Einzelitems ermöglichen aktuell keine zusätzlichen Checks oder Regionen.')
          : t('Noch keine aktuelle Analyse vorhanden. Über „Was bringt mich weiter?“ lässt sie sich für deinen Slot berechnen.');
        tools.hidden = !data.available || !hasItems;
        playerForm.hidden = !query && data.total <= pageSize;
        spoiler.hidden = !data.available;
        spoiler.textContent = revealed ? t('Fundorte ausblenden') : t('Fundorte zeigen (Spoiler)');
        pagination.hidden = data.pages <= 1;
        previous.disabled = playerPage <= 1;
        next.disabled = playerPage >= data.pages;
        $('round-item-page').textContent = t('Seite {v0} von {v1}', {v0: number.format(playerPage), v1: number.format(data.pages)});
        if (moveToResults) {
          moveToResults = false;
          results.focus({preventScroll: true});
          results.scrollIntoView({block: 'start'});
        }
      } catch (error) {
        if (request !== itemRequest) return;
        if (error.status === 403 || error.status === 401) {
          clearItems();
          tools.hidden = spoiler.hidden = true;
        }
        message.textContent = error.message;
        itemKey = '';
      }
    }

    function renderOverview(data) {
      if (!suggestion) return;
      expires = Infinity;
      analysisButton.textContent = t('Was bringt mich weiter?');
      context.textContent = '';
      if (data.state === 'ready') {
        const item = data.next_item;
        if (data.next_check) {
          suggestion.textContent = t('Prüfe {v0}.', {v0: data.next_check});
        } else if (item) {
          suggestion.textContent = t('{v0} könnte dir weiterhelfen.', {v0: item.name});
        } else {
          suggestion.textContent = t('Die Analyse hat keinen unmittelbar hilfreichen Einzelitem-Effekt gefunden.');
        }
        const notes = [];
        if (data.next_check) notes.push(data.reachable_count === 1 ? t('Laut Spiellogik erreichbar')
          : t('{v0} offene Checks laut Spiellogik', {v0: number.format(data.reachable_count)}));
        if (item) {
          notes.push(t('Ein Exemplar könnte +{v0} Checks und +{v1} Bereiche öffnen.', {v0: number.format(item.checks), v1: number.format(item.regions)}));
          if (item.finders.length) notes.push(t('In der Welt von {v0}', {v0: formatFinders(item.finders)}));
        }
        if (!data.singles_complete && !data.next_check) notes.push(t('Teilweise analysiert'));
        if (data.observed_at) {
          notes.push(t('Inventarstand {v0}', {v0: date.format(data.observed_at * 1000)}));
          expires = data.observed_at * 1000 + 300000;
        }
        context.textContent = notes.join(' · ');
        analysisButton.textContent = t('Analyse ansehen');
      } else if (data.state === 'loading') {
        suggestion.textContent = t('Die Spielregeln werden im Hintergrund geprüft …');
      } else if (data.state === 'unsupported') {
        suggestion.textContent = data.reason === 'inventory_missing'
          ? t('Für die Logikhilfe fehlt ein aktueller Inventarstand.')
          : t('Für diesen Stand ist keine Logikhilfe verfügbar.');
      } else if (data.state === 'idle') {
        suggestion.textContent = t('Prüfe, welche Checks oder Items dich weiterbringen könnten.');
      } else {
        suggestion.textContent = t('Logikhilfe für dein gemeldetes Inventar.');
      }
    }

    async function loadOverview(reset = false) {
      clearTimeout(overviewTimer);
      const request = ++overviewRequest;
      if (reset) renderOverview({state: 'hidden'});
      if (!suggestion || !visible() || !sheet.dataset.own || !revealed || root.open) return;
      const params = new URLSearchParams({slot: sheet.dataset.slot, overview: '1'});
      try {
        const data = await api('/analysis?' + params);
        if (request !== overviewRequest || !revealed) return;
        renderOverview(data);
        if (focus === 'useful' && data.state !== overviewState) {
          itemKey = '';
          loadPlayerItems();
        }
        overviewState = data.state;
        if (data.state === 'loading') overviewTimer = setTimeout(loadOverview, 1500);
      } catch (error) {
        if (request === overviewRequest) renderOverview({state: 'unsupported'});
      }
    }

    function search() {
      clearTimeout(queryTimer);
      playerPage = 1;
      chooseInitialView = false;
      loadPlayerItems();
    }

    playerForm.addEventListener('submit', event => { event.preventDefault(); search(); });
    playerForm.elements.q.addEventListener('input', () => {
      clearTimeout(queryTimer);
      queryTimer = setTimeout(search, 180);
    });
    for (const button of views) button.addEventListener('click', () => {
      if (focus === button.dataset.roundItemView) return;
      chooseInitialView = false;
      setFocus(button.dataset.roundItemView);
      clearItems();
      loadPlayerItems();
    });
    spoiler.addEventListener('click', async () => {
      spoiler.disabled = true;
      try {
        const state = await api('/consent', {reveal: revealed ? '0' : '1'});
        consent(state.revealed);
      } catch (error) { message.textContent = error.message; }
      finally { spoiler.disabled = false; }
    });
    function turnPage(offset) {
      playerPage += offset;
      moveToResults = true;
      loadPlayerItems();
    }
    previous.addEventListener('click', () => turnPage(-1));
    next.addEventListener('click', () => turnPage(1));
    document.addEventListener('hub:round-player', () => {
      clearTimeout(queryTimer);
      playerForm.reset();
      chooseInitialView = true;
      setFocus('open');
      itemKey = '';
      itemRequest++;
      clearItems();
      tools.hidden = spoiler.hidden = true;
      loadPlayerItems();
      loadOverview(true);
    });
    document.addEventListener('hub:round-players-visible', () => {
      loadPlayerItems();
      loadOverview(true);
    });
    document.addEventListener('hub:progression-consent', () => {
      if (!revealed) {
        if (focus === 'help' || focus === 'useful') {
          setFocus('open');
          chooseInitialView = true;
          clearItems();
        } else {
          results.querySelectorAll('details, .round-item-source').forEach(details => details.remove());
        }
        views.filter(button => ['help', 'useful'].includes(button.dataset.roundItemView)).forEach(button => { button.hidden = true; });
        spoiler.textContent = t('Fundorte zeigen (Spoiler)');
      }
      itemKey = '';
      itemRequest++;
      loadPlayerItems();
      loadOverview(true);
    });
    document.addEventListener('hub:progression-closed', () => {
      loadOverview();
      if (focus === 'useful') {
        itemKey = '';
        loadPlayerItems();
      }
    });
    document.addEventListener('hub:round-data', event => {
      const updated = JSON.stringify(event.detail);
      if (updated !== version) {
        version = updated;
        loadPlayerItems();
        loadOverview(Date.now() >= expires);
      } else if (Date.now() >= expires) {
        loadOverview(true);
      }
    });
    document.addEventListener('visibilitychange', () => {
      if (!visible()) return;
      loadPlayerItems();
      loadOverview(Date.now() >= expires);
    });
    loadPlayerItems();
    loadOverview(true);
  }

  async function find(){
    const current=++sequence,params=new URLSearchParams(new FormData($('progression-search')));params.set('page',page);
    try{
      const data=await api('/items?'+params);
      if(current!==sequence||!revealed)return;
      pages=data.pages||1;page=data.page;
      $('progression-results').replaceChildren(...data.rows.map(placement));
      $('progression-count').textContent=data.available?t('Gefundene Items')+': '+data.total:reasons.placements_missing;
      $('progression-page').textContent=page+' / '+pages;
      $('progression-previous').disabled=page<=1;$('progression-next').disabled=page>=pages;
    }catch(error){if(current===sequence)fail(error.message);}
  }
  $('progression-search').addEventListener('submit',event=>{event.preventDefault();page=1;find();});
  $('progression-search').querySelectorAll('select').forEach(n=>n.addEventListener('change',()=>{page=1;find();}));
  $('progression-previous').addEventListener('click',()=>{page--;find();});
  $('progression-next').addEventListener('click',()=>{page++;find();});
  function recommendation(row){
    const box=node('article',null,'progression-item progression-recommendation');
    const item=row.items[0];
    box.append(node('h4',item.name),node('p','+'+row.new_checks.length+' '+t('zusätzliche Checks')+' · +'+row.new_regions.length+' '+t('neue Bereiche')));
    if(row.target_gain)box.append(node('p',t('Der gewählte Bereich wird erreichbar'),'ok'));
    const placements=item.placements||[];
    if(placements.length)box.append(placement(placements[0]));
    else box.append(node('p',t('Kein verifizierter Fundort verfügbar.'),'muted small'));
    if(placements.length>1){
      const found=node('details');found.append(node('summary',t('Weitere Exemplare und Fundorte')+' ('+(placements.length-1)+')'));
      placements.slice(1).forEach(p=>found.append(placement(p)));box.append(found);
    }
    function locations(checks,regions,label){
      const detail=node('details');detail.append(node('summary',label));const list=node('ul');
      checks.forEach(id=>list.append(node('li',analysisTargets.find(l=>l.id===id)?.name||String(id))));regions.forEach(name=>list.append(node('li',name)));
      detail.append(list);box.append(detail);
    }
    locations(row.new_checks,row.new_regions,t('Neue Checks und Bereiche ansehen'));
    return box;
  }
  function normalize(data){
    // Ignore legacy cached pair results. Only one additional copy per type is
    // eligible, regardless of older backend or cache response shapes.
    const seen=new Set();
    data.singles=(data.singles||[]).filter(row=>{
      if(row.items?.length!==1||row.items[0].count!==1||seen.has(row.items[0].name))return false;
      seen.add(row.items[0].name);row.helpful=Boolean(row.new_checks.length||row.new_regions.length);
      row.target_gain=Boolean(row.target_reached&&!data.target_reachable);return true;
    });
    data.singles.sort((a,b)=>b.new_checks.length-a.new_checks.length||b.new_regions.length-a.new_regions.length||
      a.items[0].name.toLowerCase().localeCompare(b.items[0].name.toLowerCase(),'en')||a.items[0].name.localeCompare(b.items[0].name,'en'));
    return data;
  }
  function recommendationSection(rows,label,emptyText,kind){
    const section=node('section',null,'progression-recommendations');section.dataset.recommendationKind=kind;section.append(node('h4',label));
    if(!rows.length){section.append(node('p',emptyText,'muted small'));return section;}
    rows.slice(0,10).forEach(row=>section.append(recommendation(row)));
    if(rows.length>10){
      const more=node('details',null,'progression-more');more.append(node('summary',t('Mehr anzeigen')+' ('+(rows.length-10)+')'));
      rows.slice(10).forEach(row=>more.append(recommendation(row)));section.append(more);
    }
    return section;
  }
  let analysisTargets=[];
  function renderAnalysis(data,mode){
    const isGoal=mode==='goal',state=$(isGoal?'progression-goal-status':'progression-analysis-state');
    state.textContent=data.state==='ready'?t('Spielregeln und Seed stimmen überein'):data.state==='loading'?t('Die Spielregeln werden im Hintergrund geprüft …'):data.state==='idle'?t('Starte die Berechnung bei Bedarf ausdrücklich.'):data.state==='busy'?t('Die Analyse ist ausgelastet. Bitte kurz warten.'):reasons[data.reason]||reasons.worker_failed;
    if(isGoal){
      $('progression-goals').replaceChildren();
      if(data.state!=='ready')return;
      state.textContent=data.goal_reachable?t('Spielziel mit deinem gemeldeten Inventar erreichbar'):t('Spielziel mit deinem gemeldeten Inventar noch nicht erreichbar');
      if(!data.necessity_complete)$('progression-goals').append(node('p',t('Die Zielprüfung ist unvollständig. Fehlende Ergebnisse beweisen keine Unmöglichkeit.'),'warn small'));
      const verdict={necessary:t('Nachweislich notwendiges Exemplar'),replaceable_copy:t('Dieses Einzel-exemplar ist ersetzbar'),unknown:t('Noch nicht zuverlässig bestimmbar')};
      (data.necessity||[]).forEach(row=>{const box=node('article',null,'progression-item');box.append(node('h4',row.item),node('p',verdict[row.verdict]));if(row.placement)box.append(placement(row.placement));$('progression-goals').append(box);});
      return;
    }
    $('progression-observed').textContent=data.observed_at?t('Inventarstand')+': '+observation(data.observed_at):'';
    $('progression-spheres').replaceChildren();
    (data.static?.spheres||[]).forEach(s=>{$('progression-spheres').append(node('p',(s.unreachable?t('Nicht erreichbar'):t('Schritt')+' '+s.number)+': '+s.locations.map(l=>l.name).join(', '),'small'));});
    $('progression-helpful').replaceChildren();$('progression-reachable').replaceChildren();
    if(data.state!=='ready')return;
    data=normalize(data);analysisTargets=data.targets||[];
    const target=$('progression-target');
    if(target){
      const selected=target.value,choices=[new Option(t('Allgemeine Hilfe'),'')];
      analysisTargets.forEach(loc=>choices.push(new Option(loc.name,'location:'+loc.id)));
      [...new Set(analysisTargets.map(loc=>loc.region))].forEach(name=>choices.push(new Option(name,'region:'+name)));
      target.replaceChildren(...choices);target.value=selected||'';
    }
    $('progression-support').textContent=data.singles_complete?t('Verifizierte Logikhilfe'):t('Teilweise Unterstützung');
    $('progression-helpful').append(node('p',(data.reachable||[]).length+' '+t('aktuell erreichbare, offene Checks')));
    $('progression-helpful').append(node('p',data.singles_tested+' '+t('von')+' '+data.candidates_total+' '+t('Progression-Itemarten untersucht'),'small progression-coverage'));
    if(!data.singles_complete)$('progression-helpful').append(node('p',t('Die Analyse ist unvollständig. Nicht untersuchte Items wurden nicht als unwichtig eingestuft.'),'warn small'));
    $('progression-helpful').append(recommendationSection(data.singles.filter(row=>row.helpful),t('Einzelne hilfreiche Items'),t('Unter den geprüften Einzelitems wurde kein unmittelbarer Zusatznutzen gefunden.'),'singles'));
    const zero=data.singles.filter(row=>!row.helpful);
    if(zero.length){
      const detail=node('details',null,'progression-zero');detail.append(node('summary',t('Weitere untersuchte Items ohne unmittelbaren Einzeleffekt')+' ('+zero.length+')'));
      detail.append(node('p',t('Diese Items können später oder zusammen mit anderen Items wichtig sein.'),'small muted'));
      zero.forEach(row=>detail.append(recommendation(row)));$('progression-helpful').append(detail);
    }
    (data.reachable||[]).forEach(loc=>$('progression-reachable').append(node('li',loc.name+' · '+loc.region)));
  }
  let pendingAnalysis=null;
  async function analysis(start){
    if(!revealed||!root.open)return;
    if(analysisBusy){pendingAnalysis={start:start||Boolean(pendingAnalysis?.start),view};return;}
    const mode=view==='goal'?'goal':'items',form=$(mode==='goal'?'progression-goal-analyze':'progression-analyze');
    if(!form)return;
    analysisBusy=true;clearTimeout(timer);fail('');
    const settings=Object.fromEntries(new FormData(form));settings.mode=mode;
    const target=mode==='items'?$('progression-target')?.value||'':'';
    if(target.startsWith('location:')){settings.target_kind='location';settings.target_id=target.slice(9);}
    if(target.startsWith('region:')){settings.target_kind='region';settings.target_name=target.slice(7);}
    const selectedSlot=settings.slot;
    try{
      const data=await api('/analysis'+(start?'':'?'+new URLSearchParams(settings)),start?settings:null);
      if(!revealed||form.elements.slot.value!==selectedSlot||(view==='goal'?'goal':'items')!==mode||
         (mode==='items'&&target!==($('progression-target')?.value||'')))return;
      renderAnalysis(data,mode);
      if(data.state==='loading'&&root.open)timer=setTimeout(()=>analysis(false),1200);
    }catch(error){fail(error.message);}finally{analysisBusy=false;if(pendingAnalysis){const pending=pendingAnalysis;pendingAnalysis=null;analysis(pending.view===view&&pending.start);}}
  }
  ['progression-analyze','progression-goal-analyze'].forEach(id=>{
    $(id)?.addEventListener('submit',event=>{event.preventDefault();analysis(true);});
    $(id)?.elements.slot.addEventListener('change',()=>{
      if(id==='progression-analyze'&&$('progression-target'))$('progression-target').replaceChildren(new Option(t('Allgemeine Hilfe'),''));
      analysis(false);
    });
  });
  $('progression-target')?.addEventListener('change',()=>analysis(false));
  if(root.dataset.standalone)open('finder');
})();
