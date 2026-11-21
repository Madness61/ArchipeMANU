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
        if(select && select.value!==selected && [...select.options].some(option=>option.value===selected)){
          select.value=selected;
          if (id==='progression-analyze') $('progression-target')?.replaceChildren(new Option(t('Allgemeine Hilfe'),''));
        }
      }
    }
    open(button.dataset.progressionOpen);
  }));
  root.querySelectorAll('[data-progression-tab]').forEach(button=>button.addEventListener('click',()=>selectTab(button.dataset.progressionTab)));
  $('progression-close').addEventListener('click',()=>root.close());
  root.addEventListener('close',()=>{clearTimeout(timer);sequence++;consent(revealed);});
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
    const results = $('round-item-list');
    const message = $('round-item-result-status');
    const spoiler = $('round-item-spoilers');
    const pagination = $('round-item-pagination');
    const previous = $('round-item-previous');
    const next = $('round-item-next');
    const receiptLabels = {
      received: t('Bestätigt erhalten'), not_received: t('Noch nicht erhalten'), unknown: t('Empfang unbekannt')
    };
    let playerPage = 1, requestNumber = 0, lastVersion, loading = false, focus = 'needed', searchTimer;
    let requestedSlot = '';
    const visible = () => !panel.closest('[data-round-panel]').hidden;

    function itemRow(group, expanded) {
      const row = node('li', null, 'round-item');
      row.dataset.item = group.name;
      const heading = node('div', null, 'row spread');
      heading.append(node('strong', group.name + (group.total > 1 ? ' × ' + group.total : '')));
      if(focus==='help') heading.append(node('span',t('Für {v0}',{v0:group.recipient}),'round-item-recipient'));
      const counts = node('div', null, 'row round-item-counts');
      for (const [status, label] of Object.entries(receiptLabels)) {
        if (group[status]) counts.append(node('span', group[status] + ' ' + label, 'chip ' + (status === 'received' ? 'ok' : '')));
      }
      heading.append(counts);
      row.append(heading);
      if(group.found) row.append(node('p',t('{v0} gefunden · Empfang noch offen',{v0:group.found}),'round-item-delivery'));
      if(group.effect) row.append(node('p',t('+{v0} Checks · +{v1} Regionen mit einem Exemplar',
        {v0:group.effect.checks,v1:group.effect.regions}),'round-item-effect'));
      if (group.copies?.length) {
        const locations = node('details');
        locations.open = expanded;
        locations.append(node('summary', t('Fundorte')));
        const copies = node('ul');
        for (const copy of group.copies) {
          const item = node('li');
          const status = inlineStatus[copy.check_status] + ' · ' + receiptLabels[copy.status];
          const finder=node('a',copy.finder);
          const target=[...document.querySelectorAll('[data-round-player]')].find(choice=>choice.dataset.roundPlayer===copy.finder);
          if(target) finder.href='#'+target.id;
          item.append(node('strong', copy.location), finder, node('small', copy.game + ' · ' + status));
          copies.append(item);
        }
        locations.append(copies);
        row.append(locations);
      }
      return row;
    }

    async function loadPlayerItems(reset = false) {
      if (!visible() || !sheet.dataset.slot) return;
      const slot = sheet.dataset.slot;
      if (reset || slot !== requestedSlot) {
        playerPage = 1;
        results.replaceChildren();
        pagination.hidden = true;
        message.textContent = t('Progression-Items werden geladen …');
      }
      requestedSlot = slot;
      const request = ++requestNumber;
      const params = new URLSearchParams(new FormData(playerForm));
      params.set('recipient', slot);
      params.set('page', playerPage);
      params.set('limit', '12');
      params.set('focus', focus);
      loading = true;
      try {
        const data = await api('/items?' + params);
        if (request !== requestNumber) return;
        if (revealed !== data.revealed) {
          consent(data.revealed);
          return;
        }
        const expanded = new Set([...results.querySelectorAll('details[open]')].map(detail => detail.closest('li').dataset.item));
        results.replaceChildren(...data.rows.map(group => itemRow(group, expanded.has(group.name))));
        playerPage = data.page;
        const contexts={
          needed:t('Fehlende Items zuerst. Unbekannter Empfang bleibt ausdrücklich gekennzeichnet.'),
          found:t('Der Fund ist bestätigt. Der Empfang ist bisher nicht bestätigt.'),
          help:t('Hier liegen Progression-Items für andere Spieler. Fundorte erfordern deine Spoilerfreigabe.'),
          useful:t('Zusätzliche Checks und Regionen laut vorhandener Inventaranalyse.'),
          all:t('Alle Progression-Items dieses Spielers, einschließlich bestätigter Empfänge.')
        };
        $('round-item-context').textContent=contexts[focus];
        for(const badge of panel.querySelectorAll('[data-view-count]')){
          const count=badge.dataset.viewCount==='all'?null:badge.dataset.viewCount==='useful'?data.helpful:data.counts?.[badge.dataset.viewCount];
          badge.textContent=count==null?'':String(count);
        }
        message.textContent = !data.available ? reasons.placements_missing
          : focus==='help'&&!revealed ? t('Gib die Fundort-Spoiler frei, um Hilfe zwischen Spielern zu sehen.')
          : focus==='useful'&&data.analysis_state==='ready'&&!data.helpful ? t('Die geprüften Einzelitems ermöglichen aktuell keine zusätzlichen Checks oder Regionen.')
          : focus==='useful'&&!data.helpful ? t('Noch keine aktuelle Analyse vorhanden. Über „Was bringt mich weiter?“ lässt sie sich für deinen Slot berechnen.')
          : data.total ? t('{v0} Treffer', {v0: data.total.toLocaleString(window.HUB_I18N.locale)})
          : focus==='needed' ? t('Alle erfassten Progression-Items sind bestätigt empfangen.') : t('Keine passenden Progression-Items.');
        spoiler.hidden = !data.available;
        spoiler.textContent = revealed ? t('Spoiler wieder sperren') : t('Fundort-Spoiler bewusst freigeben');
        pagination.hidden = data.pages <= 1;
        previous.disabled = playerPage <= 1;
        next.disabled = playerPage >= data.pages;
        $('round-item-page').textContent = playerPage + ' / ' + data.pages;
      } catch (error) {
        if (request === requestNumber) message.textContent = error.message;
      } finally {
        if (request === requestNumber) loading = false;
      }
    }
    playerForm.addEventListener('submit', event => { event.preventDefault(); loadPlayerItems(true); });
    playerForm.elements.q.addEventListener('input',()=>{
      clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadPlayerItems(true),300);
    });
    for(const button of panel.querySelectorAll('[data-item-view]')){
      button.addEventListener('click',()=>{
        focus=button.dataset.itemView;
        for(const tab of panel.querySelectorAll('[data-item-view]'))tab.setAttribute('aria-pressed',String(tab===button));
        loadPlayerItems(true);
      });
    }
    root.addEventListener('close',()=>loadPlayerItems());
    spoiler.addEventListener('click', async () => {
      spoiler.disabled = true;
      try {
        const state = await api('/consent', {reveal: revealed ? '0' : '1'});
        consent(state.revealed);
      } catch (error) { message.textContent = error.message; }
      finally { spoiler.disabled = false; }
    });
    previous.addEventListener('click', () => { playerPage--; loadPlayerItems(); });
    next.addEventListener('click', () => { playerPage++; loadPlayerItems(); });
    document.addEventListener('hub:round-player', () => loadPlayerItems(true));
    document.addEventListener('hub:round-players-visible', () => { if (!loading) loadPlayerItems(); });
    document.addEventListener('hub:progression-consent', () => {
      if (!revealed) results.querySelectorAll('details').forEach(details => details.remove());
      loadPlayerItems();
    });
    document.addEventListener('hub:round-data', event => {
      const version = JSON.stringify(event.detail);
      if (version !== lastVersion && !loading) {
        lastVersion = version;
        loadPlayerItems();
      }
    });
    loadPlayerItems();
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
