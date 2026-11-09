(() => {
  const root=document.getElementById('logic-tracker'); if(!root)return;
  const $=id=>document.getElementById(id), base=root.dataset.base;
  let state=null, placements=new Map(), busy=false, generation=0;
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const api=async(path,body)=>{
    const options=body ? {method:'POST',headers:{'X-CSRF-Token':root.dataset.csrf},body:new URLSearchParams(body)} : {};
    const response=await fetch(base+path,{...options,cache:'no-store'});
    const data=await response.json().catch(()=>({error:'Die Antwort konnte nicht gelesen werden.'}));
    if(!response.ok)throw new Error(data.error||'Die Anfrage konnte nicht abgeschlossen werden.');return data;
  };
  function clear(){state=null;placements.clear();$('logic-reachable').textContent='—';$('logic-remaining').textContent='—';$('logic-go').textContent='Unbekannt';$('logic-inventory').replaceChildren();$('logic-count').textContent='Noch keine Berechnung';$('logic-locations').replaceChildren(node('p','Für den aktuellen Serverstand liegen noch keine Logikdaten vor.','muted'));}
  function render(){
    const query=$('logic-search').value.toLocaleLowerCase('de'),filter=$('logic-filter').value;
    const locations=(state?.locations||[]).filter(loc=>{
      const matches=filter==='all'||filter==='open'&&!loc.checked||filter==='checked'&&loc.checked||filter==='reachable'&&loc.reachable&&!loc.checked||filter==='blocked'&&!loc.reachable&&!loc.checked;
      return matches&&[loc.name,loc.region,placements.get(loc.id)?.item||''].join(' ').toLocaleLowerCase('de').includes(query);
    });
    $('logic-count').textContent=locations.length+' passende Checks';
    const rows=locations.map(loc=>{const card=node('article',null,'logic-location');const label=loc.checked?'Erledigt':loc.reachable?'In Logic':'Außerhalb der Logik';card.dataset.state=loc.checked?'checked':loc.reachable?'reachable':'blocked';card.append(node('span',label,'chip'),node('h3',loc.name),node('p',loc.region,'muted small'));const item=placements.get(loc.id);if(item)card.append(node('p',item.item+' → '+item.recipient,'small'));return card;});
    $('logic-locations').replaceChildren(...(rows.length?rows:[node('p','Keine Checks für diese Auswahl.','muted')]));
  }
  async function update(refresh=false){
    if(busy)return;busy=true;let recalculate=false;const ticket=generation,slot=$('logic-slot').value;
    try{
      const data=await api(refresh?'/refresh':'/data?'+new URLSearchParams({slot}),refresh?{slot}:null);
      if(ticket!==generation)return;
      recalculate=!refresh&&['idle','stale'].includes(data.state)&&$('logic-auto').checked;
      if(data.state!=='ready'){clear();$('logic-status').textContent=data.error||'Noch keine Logikdaten.';$('logic-status').dataset.error=String(!['loading','idle'].includes(data.state));}
      else {state=data;$('logic-status').textContent=data.engine+' · Datenstand '+new Date(data.observed_at*1000).toLocaleTimeString('de-DE')+(data.deferred_entrances?' · '+data.deferred_entrances+' noch unbekannte Verbindungen':'');$('logic-status').dataset.error='false';$('logic-reachable').textContent=data.reachable;$('logic-remaining').textContent=data.remaining;$('logic-go').textContent=data.go_mode==null?'Unbekannt':data.go_mode?'Ja':'Noch nicht';$('logic-inventory').replaceChildren(...data.inventory.map(i=>node('li',i.count+' × '+i.name)));render();}
    }catch(error){if(ticket===generation){clear();$('logic-status').textContent=error.message;$('logic-status').dataset.error='true';}}
    finally{busy=false;if(recalculate&&ticket===generation)update(true);}
  }
  $('logic-refresh').addEventListener('click',()=>update(true));
  $('logic-auto').addEventListener('change',()=>update());
  $('logic-slot').addEventListener('change',()=>{generation++;clear();update();});
  $('logic-search').addEventListener('input',render);$('logic-filter').addEventListener('change',render);
  $('logic-reveal').addEventListener('click',async()=>{const ticket=generation;try{const data=await api('/placements',{slot:$('logic-slot').value});if(ticket!==generation)return;placements=new Map(data.placements.map(row=>[row.id,row]));render();$('logic-reveal').textContent='Iteminhalte aufgedeckt';}catch(error){$('logic-status').textContent=error.message;}});
  $('logic-install')?.addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;try{await api('/install',{});button.hidden=true;update();}catch(error){$('logic-status').textContent=error.message;}finally{button.disabled=false;}});
  setInterval(()=>{if(!document.hidden)update();},5000);update();
})();
