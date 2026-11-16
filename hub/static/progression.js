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
    const combined=row.items.reduce((sum,item)=>sum+item.count,0)>1;
    box.append(node('h4',row.items.map(i=>i.name+(i.count>1?' × '+i.count:'')).join(' + ')),
      node('p',(combined?t('Gesamteffekt')+': ':'')+'+'+row.new_checks.length+' '+t('zusätzliche Checks')+' · +'+row.new_regions.length+' '+t('neue Bereiche')));
    if(combined){
      box.append(node('p',t('Nur durch diese Kombination')+': +'+row.synergy.checks.length+' '+t('zusätzliche Checks')+' · +'+row.synergy.regions.length+' '+t('neue Bereiche'),'progression-synergy'));
      if(row.synergy.goal)box.append(node('p',t('Dieses Paar erreicht das Spielziel; keines seiner Einzelitems reicht dafür.'),'ok'));
      if(row.synergy.target)box.append(node('p',t('Dieses Paar erreicht das gewählte Ziel; keines seiner Einzelitems reicht dafür.'),'ok'));
    }
    if(row.goal_gain)box.append(node('p',t('Spielziel mit diesem Inventar erreichbar'),'ok'));
    if(row.target_gain)box.append(node('p',t('Der gewählte Bereich wird erreichbar'),'ok'));
    const found=node('details');found.append(node('summary',t('Konkrete Fundorte ansehen')));
    row.items.forEach(item=>(item.placements||[]).forEach(p=>found.append(placement(p))));box.append(found);
    function locations(checks,regions,label){
      const detail=node('details');detail.append(node('summary',label));const list=node('ul');
      checks.forEach(id=>list.append(node('li',analysisTargets.find(l=>l.id===id)?.name||String(id))));regions.forEach(name=>list.append(node('li',name)));
      detail.append(list);box.append(detail);
    }
    if(combined)locations(row.synergy.checks,row.synergy.regions,t('Zusätzliche Checks und Bereiche ansehen'));
    locations(row.new_checks,row.new_regions,combined?t('Gesamten Effekt ansehen'):t('Neue Checks und Bereiche ansehen'));
    return box;
  }
  function normalize(data){
    // Old in-flight/cached API responses also need set-based suppression. An
    // absent single trial is unknown, never equivalent to a zero-item effect.
    const target=$('progression-target')?.value||'';
    const targetKnown=data.target_reachable ?? (target.startsWith('location:')?data.reachable.some(l=>l.id===Number(target.slice(9))):target.startsWith('region:')?(data.regions||[]).includes(target.slice(7)):false);
    const annotate=row=>{
      row.goal_gain=Boolean(row.goal_reachable&&!data.goal_reachable);
      row.target_gain=Boolean(row.target_reached&&!targetKnown);
      row.helpful=Boolean(row.new_checks.length||row.new_regions.length||row.goal_gain||row.target_gain);
    };
    data.singles.forEach(annotate);
    const singles=new Map(data.singles.map(row=>[row.items[0].name,row])),seen=new Set();
    data.combinations=data.combinations.filter(row=>{
      annotate(row);
      const identity=JSON.stringify(row.items.map(i=>[i.name,i.count]).sort());
      if(seen.has(identity))return false;seen.add(identity);
      const parts=row.items.map(i=>singles.get(i.name));if(parts.some(p=>!p))return false;
      const checks=new Set(parts.flatMap(p=>p.new_checks)),regions=new Set(parts.flatMap(p=>p.new_regions));
      row.synergy={checks:row.new_checks.filter(id=>!checks.has(id)),regions:row.new_regions.filter(name=>!regions.has(name)),
        goal:row.goal_gain&&!parts.some(p=>p.goal_gain),target:row.target_gain&&!parts.some(p=>p.target_gain)};
      return Boolean(row.synergy.checks.length||row.synergy.regions.length||row.synergy.goal||row.synergy.target);
    });
    const rank=row=>[-Number(row.target_gain),-Number(row.goal_gain),-(row.synergy?.checks.length??row.new_checks.length),-(row.synergy?.regions.length??row.new_regions.length),-row.new_checks.length,-row.new_regions.length];
    const compare=(a,b)=>{const x=rank(a),y=rank(b);for(let i=0;i<x.length;i++)if(x[i]!==y[i])return x[i]-y[i];return 0;};
    data.singles.sort(compare);data.combinations.sort(compare);
    return data;
  }
  function recommendationSection(rows,label,emptyText,kind){
    const section=node('section',null,'progression-recommendations');section.dataset.recommendationKind=kind;section.append(node('h4',label));
    if(!rows.length){section.append(node('p',emptyText,'muted small'));return section;}
    const groups=new Map();
    rows.forEach(row=>{
      const key=JSON.stringify([row.new_checks.slice().sort((a,b)=>a-b),row.new_regions.slice().sort(),row.goal_gain,row.target_gain,
        row.synergy?[row.synergy.checks.slice().sort((a,b)=>a-b),row.synergy.regions.slice().sort(),row.synergy.goal,row.synergy.target]:null]);
      if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);
    });
    let overflow=null,index=0;
    groups.forEach(recipes=>{
      const box=node('div',null,'progression-effect-group');box.append(recommendation(recipes[0]));
      if(recipes.length>1){
        const alternatives=node('details',null,'progression-alternatives');alternatives.append(node('summary',t('Alternativen mit derselben Wirkung')+' ('+(recipes.length-1)+')'));
        recipes.slice(1).forEach(row=>alternatives.append(recommendation(row)));box.append(alternatives);
      }
      if(index++<6)section.append(box);
      else{
        if(!overflow){overflow=node('details',null,'progression-more');overflow.append(node('summary',t('Weitere Empfehlungen')+' ('+(groups.size-6)+')'));section.append(overflow);}
        overflow.append(box);
      }
    });return section;
  }
  let analysisTargets=[];
  function renderAnalysis(data){
    const state=$('progression-analysis-state');
    state.textContent=data.state==='ready'?t('Spielregeln und Seed stimmen überein'):data.state==='loading'?t('Die Spielregeln werden im Hintergrund geprüft …'):data.state==='idle'?t('Berechne deine nächsten Möglichkeiten mit dem gemeldeten Inventar.'):data.state==='busy'?t('Die Analyse ist ausgelastet. Bitte kurz warten.'):reasons[data.reason]||reasons.worker_failed;
    $('progression-observed').textContent=data.observed_at?t('Inventarstand')+': '+observation(data.observed_at):'';
    $('progression-spheres').replaceChildren();
    (data.static?.spheres||[]).forEach(s=>{$('progression-spheres').append(node('p',(s.unreachable?t('Nicht erreichbar'):t('Schritt')+' '+s.number)+': '+s.locations.map(l=>l.name).join(', '),'small'));});
    $('progression-helpful').replaceChildren();$('progression-reachable').replaceChildren();$('progression-goals').replaceChildren();
    $('progression-goal-status').textContent=t('Noch nicht zuverlässig bestimmbar');
    if(data.state!=='ready')return;
    data=normalize(data);
    $('progression-support').textContent=data.singles_complete&&data.combinations_complete&&data.necessity_complete?t('Verifizierte Logikhilfe'):t('Teilweise Unterstützung');
    analysisTargets=data.targets;
    const selected=$('progression-target')?.value;
    if($('progression-target')){
      const choices=[new Option(t('Allgemeine Hilfe'),'')];
      data.targets.forEach(loc=>choices.push(new Option(loc.name,'location:'+loc.id)));
      [...new Set(data.targets.map(loc=>loc.region))].forEach(name=>choices.push(new Option(name,'region:'+name)));
      $('progression-target').replaceChildren(...choices);$('progression-target').value=selected||'';
    }
    $('progression-helpful').append(node('p',data.reachable.length+' '+t('aktuell erreichbare, offene Checks')));
    if(!data.singles_complete||!data.combinations_complete||!data.necessity_complete)$('progression-helpful').append(node('p',t('Begrenzte Analyse: Nicht alle Items, Paare oder Zielprüfungen wurden untersucht. Fehlende Ergebnisse beweisen keine Unmöglichkeit.'),'warn small'));
    if(Number.isInteger(data.combinations_tested)&&Number.isInteger(data.combinations_total))$('progression-helpful').append(node('p',data.combinations_tested+' '+t('von')+' '+data.combinations_total+' '+t('möglichen Itemkombinationen untersucht'),'small progression-coverage'));
    if(Number.isInteger(data.singles_tested))$('progression-helpful').append(node('p',data.singles_tested+' '+t('von')+' '+data.candidates_total+' '+t('Itemarten einzeln untersucht'),'small muted'));
    $('progression-helpful').append(recommendationSection(data.singles.filter(row=>row.helpful),t('Einzelne hilfreiche Items'),t('Unter den geprüften Einzelitems wurde kein unmittelbarer Zusatznutzen gefunden.'),'singles'));
    $('progression-helpful').append(recommendationSection(data.combinations,t('Echte Itemkombinationen'),t('Unter den geprüften Paaren wurde kein zusätzlicher Kombinationseffekt gefunden.'),'combinations'));
    const zero=data.singles.filter(row=>!row.helpful);
    if(zero.length){const detail=node('details');detail.append(node('summary',t('Weitere untersuchte Items ohne unmittelbaren Einzeleffekt')+' ('+zero.length+')'));const list=node('ul');zero.forEach(row=>list.append(node('li',row.items[0].name)));detail.append(list);$('progression-helpful').append(detail);}
    data.reachable.forEach(loc=>$('progression-reachable').append(node('li',loc.name+' · '+loc.region)));
    $('progression-goal-status').textContent=data.goal_reachable?t('Spielziel mit deinem gemeldeten Inventar erreichbar'):t('Spielziel mit deinem gemeldeten Inventar noch nicht erreichbar');
    const verdict={necessary:t('Nachweislich notwendiges Exemplar'),replaceable_copy:t('Dieses Einzel-exemplar ist ersetzbar'),unknown:t('Noch nicht zuverlässig bestimmbar')};
    data.necessity.forEach(row=>{const box=node('article',null,'progression-item');box.append(node('h4',row.item),node('p',verdict[row.verdict]));if(row.placement)box.append(placement(row.placement));$('progression-goals').append(box);});
  }
  async function analysis(start){
    if(analysisBusy||!$('progression-analyze')||!revealed)return;
    analysisBusy=true;clearTimeout(timer);fail('');
    const settings=Object.fromEntries(new FormData($('progression-analyze'))),target=$('progression-target').value;
    if(target.startsWith('location:')){settings.target_kind='location';settings.target_id=target.slice(9);}
    if(target.startsWith('region:')){settings.target_kind='region';settings.target_name=target.slice(7);}
    const selectedSlot=settings.slot;
    try{
      const data=await api('/analysis'+(start?'':'?'+new URLSearchParams(settings)),start?settings:null);
      if(!revealed||$('progression-analyze').elements.slot.value!==selectedSlot)return;
      renderAnalysis(data);
      if(data.state==='loading'&&root.open)timer=setTimeout(()=>analysis(false),1200);
    }catch(error){fail(error.message);}finally{analysisBusy=false;}
  }
  $('progression-analyze')?.addEventListener('submit',event=>{event.preventDefault();analysis(true);});
  $('progression-analyze')?.elements.slot.addEventListener('change',()=>{analysisTargets=[];$('progression-target').replaceChildren(new Option(t('Allgemeine Hilfe'),''));analysis(false);});
  if(root.dataset.standalone)open('finder');
})();
