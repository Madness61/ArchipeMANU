/* Optional spoiler-gated help. Opening a panel never starts a logic worker. */
(() => {
  const root=document.getElementById('progression-panel');
  if(!root)return;
  const t=text=>window.HUB_I18N.t(text), $=id=>document.getElementById(id);
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const labels={
    checked:t('Bereits eingesammelt'),unchecked:t('Noch nicht eingesammelt'),unknown:t('Unbekannter Status'),
    received:t('Empfang bestätigt'),not_received:t('Zu diesem Stand noch nicht empfangen'),
    progression:t('Progression'),useful:t('Useful'),filler:t('Filler'),trap:t('Trap')
  };
  const reasons={
    busy:t('Archipelago wird gerade verwendet. Bitte die Analyse später erneut starten.'),
    historical_seed:t('Für diesen älteren Seed fehlen die Rekonstruktionsdaten. Die Itemsuche bleibt verfügbar.'),
    placements_missing:t('Für diesen Seed sind keine vollständigen, verifizierten Itemplatzierungen gespeichert.'),
    inventory_missing:t('Ein vollständiger, aktueller Itemzustand fehlt. Verbinde deinen Slot in der Konsole oder warte auf den verknüpften Tracker.'),
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
  let revealed=false,view='finder',page=1,pages=1,sequence=0,analysisBusy=false,timer=null;
  const fail=text=>{$('progression-error').textContent=text;$('progression-error').hidden=!text;};
  async function api(path,body){
    const response=await fetch(root.dataset.base+path,{cache:'no-store',...(body?{method:'POST',headers:{'X-CSRF-Token':root.dataset.csrf},body:new URLSearchParams(body)}:{})});
    const data=await response.json();
    if(response.status===401)window.HUB_AUTH_REQUIRED?.(data.login_url);
    if(!response.ok)throw Error(data.error||t('Die Anfrage konnte nicht abgeschlossen werden.'));
    return data;
  }
  function selectTab(value){
    view=value;
    root.querySelectorAll('[data-progression-section]').forEach(n=>n.hidden=n.dataset.progressionSection!==view);
    root.querySelectorAll('[data-progression-tab]').forEach(n=>{if(n.dataset.progressionTab===view)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});
    if(revealed){if(view==='finder')find();else analysis(false);}
  }
  function consent(value){
    revealed=value;$('progression-consent').hidden=value;$('progression-content').hidden=!value;
    if(!value){clearTimeout(timer);$('progression-results').replaceChildren();$('progression-helpful').replaceChildren();$('progression-goals').replaceChildren();$('progression-reachable').replaceChildren();$('progression-spheres').replaceChildren();}
  }
  async function open(value){
    fail('');if(!root.open)root.showModal();
    try{const state=await api('/state');$('progression-support').textContent=state.support==='partial'?t('Teilweise Unterstützung'):t('Basisunterstützung');consent(state.revealed);selectTab(value);}
    catch(error){fail(error.message);}
  }
  document.querySelectorAll('[data-progression-open]').forEach(button=>button.addEventListener('click',()=>open(button.dataset.progressionOpen)));
  root.querySelectorAll('[data-progression-tab]').forEach(button=>button.addEventListener('click',()=>selectTab(button.dataset.progressionTab)));
  $('progression-close').addEventListener('click',()=>root.close());
  root.addEventListener('close',()=>{clearTimeout(timer);sequence++;});
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
