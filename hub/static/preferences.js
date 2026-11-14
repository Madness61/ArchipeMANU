(() => {
  const boot=JSON.parse(document.getElementById('ui-configuration').textContent);
  const messages=boot.messages||{},locale=boot.language==='en'?'en-GB':'de-DE';
  const patterns=(boot.patterns||[]).map(row=>({...row,regex:new RegExp(row.pattern,'s')}));
  const t=(message,values={})=>{
    const raw=String(message),key=raw.replace(/\s+/g,' ').trim(),fields={};let found=Object.hasOwn(messages,key),text=found?messages[key]:raw;
    if(!found){for(const row of patterns){const match=raw.trim().match(row.regex);if(match){found=true;text=row.text;row.fields.forEach((field,i)=>fields[field]=match[i+1]);break;}}}
    if(found)text=(raw.match(/^\s*/)?.[0]||'')+text+(raw.match(/\s*$/)?.[0]||'');
    Object.assign(fields,values);return text.replace(/\{(\w+)\}/g,(token,key)=>Object.hasOwn(fields,key)?String(fields[key]):token);
  };
  const playerIndex=name=>{let h=0;for(const c of String(name))h=(Math.imul(h,31)+c.codePointAt(0))>>>0;return h%8+1;};
  window.HUB_I18N={t,locale,language:boot.language};
  window.HUB_UI={playerColor:name=>'var(--player-color-'+playerIndex(name)+')'};
  const theme=mode=>{document.documentElement.dataset.theme=mode;window.dispatchEvent(new CustomEvent('hub:theme-change'));};
  document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('time[data-local-date]').forEach(node=>{const date=new Date(node.dateTime);if(!Number.isNaN(date.getTime()))node.textContent=date.toLocaleString(locale,{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});}));
  document.addEventListener('change',async event=>{
    const control=event.target.closest('[data-preference]');if(!control)return;
    const form=control.closest('form'),status=form.querySelector('[role=status]');
    if(control.dataset.preference==='theme')theme(control.value);
    control.disabled=true;
    try{
      const body=new URLSearchParams();body.set('language',form.elements.language.value);body.set('theme',form.elements.theme.value);
      const response=await fetch(boot.endpoint,{method:'POST',headers:{'X-CSRF-Token':boot.csrf,'Accept':'application/json'},body,cache:'no-store'});
      const data=await response.json();if(!response.ok)throw new Error(data.error||t('Speichern fehlgeschlagen.'));
      if(status)status.textContent=t('Gespeichert.');
      boot.theme=data.theme;
      document.querySelectorAll('[data-preference]').forEach(node=>{node.value=data[node.dataset.preference];});
      if(data.language!==boot.language)location.reload();
    }catch(error){if(control.dataset.preference==='theme'){theme(boot.theme);control.value=boot.theme;}if(status)status.textContent=error.message;}
    finally{control.disabled=false;}
  });
})();
