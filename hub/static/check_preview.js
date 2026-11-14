/* Explicit, cached reference measurement; viewing the catalog never runs AP. */
(() => {
  document.querySelectorAll('[data-check-preview]').forEach(root => {
    const button=root.querySelector('[data-check-start]'), result=root.querySelector('[data-check-result]'), status=root.querySelector('[data-check-status]');
    let busy=false, timer=null;
    async function update(start=false) {
      if(busy)return;busy=true;button.disabled=true;clearTimeout(timer);
      try {
        const response=await fetch(root.dataset.url,{cache:'no-store',...(start?{method:'POST',headers:{'X-CSRF-Token':root.dataset.csrf}}:{})});
        const data=await response.json().catch(()=>({error:window.HUB_I18N.t('Die Anfrage konnte nicht verarbeitet werden. Bitte gegebenenfalls neu anmelden.')}));
        if(response.status===401)window.HUB_AUTH_REQUIRED?.(data.login_url);
        if(!response.ok)throw new Error(data.error||window.HUB_I18N.t('Die Check-Vorschau konnte nicht abgerufen werden. Bitte kurz warten.'));
        result.textContent=data.state==='ready'?data.checks.toLocaleString(window.HUB_I18N.locale)+' Item-Checks mit Spiel-Standard':window.HUB_I18N.t('Standard-Checks noch nicht ermittelt');
        status.textContent=data.state==='ready'?'Gemessen im Referenz-Probelauf. Keine Bestätigung, dass das Spiel bereits eingerichtet ist.':data.error||'';
        button.hidden=data.state==='ready';button.disabled=data.state==='loading';
        if(data.state==='loading')timer=setTimeout(()=>update(),3000);
      } catch(error){status.textContent=error.message;button.disabled=false;}
      finally{busy=false;}
    }
    button.addEventListener('click',()=>update(true));
    if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();update();}},{rootMargin:'100px'});observer.observe(root);}
    else update();
  });
})();
