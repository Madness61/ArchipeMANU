/* Round navigation and the current player sheet. */
(() => {
  const root = document.getElementById('round-center');
  if (!root) return;

  const $ = id => document.getElementById(id);
  const {t, locale} = window.HUB_I18N;
  const nav = [...root.querySelectorAll('[data-round-view]')];
  const panels = [...root.querySelectorAll('[data-round-panel]')];
  const choices = [...root.querySelectorAll('[data-round-player]')];
  const sheet = $('round-player-detail');
  const liveStatus = $('round-live-status');
  const launch = $('round-server-start');
  const playerStates = new Map();

  let view = 'play';
  let selected = choices.find(choice => choice.dataset.own) || choices[0];
  let busy = false;
  let authLost = false;
  const number = value => value == null ? '—' : value.toLocaleString(locale);
  const ratio = (done, total) => number(done) + ' / ' + number(total);
  const percent = value => value == null ? '—' : number(value) + ' %';
  const goal = value => value === true ? t('Ziel erreicht') : value === false ? t('Ziel offen') : t('Zielstatus unbekannt');

  function renderPlayer() {
    if (!selected || !sheet) return;
    const player = playerStates.get(selected.dataset.roundPlayer) || {};
    sheet.dataset.slot = selected.dataset.roundPlayer;
    sheet.style.setProperty('--player', window.HUB_UI.playerColor(sheet.dataset.slot));
    $('round-player-name').textContent = sheet.dataset.slot;
    $('round-player-game').textContent = selected.dataset.game;
    $('round-player-checks').textContent = t('{v0} Checks · {v1}', {v0: ratio(player.checks, player.total), v1: percent(player.progress)});
    const received = $('round-player-received');
    if (received) received.textContent = t('Empfangene Items: ') + number(player.received);
    const badge = $('round-player-goal');
    badge.textContent = goal(player.goal);
    badge.classList.toggle('ok', player.goal === true);
    const actions = $('round-player-analysis');
    if (actions) actions.hidden = !selected.dataset.own;
  }

  function selectPlayer(choice) {
    if (!choice) return;
    const changed = sheet.dataset.slot !== choice.dataset.roundPlayer;
    selected = choice;
    choices.forEach(button => button.setAttribute('aria-pressed', String(button === selected)));
    renderPlayer();
    if (changed) document.dispatchEvent(new Event('hub:round-player'));
  }

  function openView() {
    let hash = location.hash.slice(1);
    try { hash = decodeURIComponent(hash); } catch {}
    const target = $(hash);
    if (hash === 'progress' || hash === 'round-progress') hash = 'players';
    view = panels.some(panel => panel.dataset.roundPanel === hash)
      ? hash : target?.closest('[data-round-panel]')?.dataset.roundPanel || 'play';
    panels.forEach(panel => { panel.hidden = panel.dataset.roundPanel !== view; });
    nav.forEach(link => {
      if (link.dataset.roundView === view) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    if (target?.matches('[data-round-player]')) selectPlayer(target);
    for (let details = target?.closest('details'); details; details = details.parentElement?.closest('details')) {
      details.open = true;
    }
    if (target && !panels.includes(target)) requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
    if (view === 'players') document.dispatchEvent(new Event('hub:round-players-visible'));
    load();
  }

  window.addEventListener('hashchange', openView);
  nav.forEach((link, index) => link.addEventListener('keydown', event => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? nav.length - 1
      : (index + (event.key === 'ArrowRight' ? 1 : -1) + nav.length) % nav.length;
    nav[next].focus();
    nav[next].click();
  }));
  root.addEventListener('click', event => {
    const setup = event.target.closest('[data-show-setup]');
    if (setup) {
      event.preventDefault();
      const box = $(setup.dataset.showSetup);
      box.hidden = !box.hidden;
      setup.setAttribute('aria-expanded', String(!box.hidden));
      if (!box.hidden) box.scrollIntoView({block: 'nearest'});
    }
    const player = event.target.closest('[data-round-player]');
    if (player) {
      selectPlayer(player);
      if (matchMedia('(max-width: 760px)').matches) sheet.focus();
    }
  });
  choices.forEach(choice => choice.style.setProperty('--player', window.HUB_UI.playerColor(choice.dataset.roundPlayer)));

  function render(data) {
    if (launch) {
      const text = window.HUB_UI.roomStartLabel(data.room_start);
      launch.hidden = !text;
      launch.textContent = data.room_start?.error || text;
    }
    if (!liveStatus) return;
    liveStatus.textContent = data.seed_matches === false
      ? t('Spieler oder Spiele des verknüpften Raums weichen von diesem Seed ab.')
      : data.updated_at
        ? t('Datenstand {v0}', {v0: new Date(data.updated_at).toLocaleTimeString(locale, {hour: '2-digit', minute: '2-digit'})})
        : t('Es liegen noch keine bestätigten Fortschrittsdaten vor.');
    $('round-checks').textContent = ratio(data.checks, data.total);
    $('round-percent').textContent = percent(data.progress);
    $('round-goals').textContent = data.known_goals ? ratio(data.goals, data.known_goals) : '—';
    for (const player of data.players) playerStates.set(player.name, player);
    for (const choice of choices) {
      const player = playerStates.get(choice.dataset.roundPlayer) || {};
      choice.querySelector('[data-player-summary]').textContent = ratio(player.checks, player.total);
      choice.querySelector('[data-player-goal]').textContent = goal(player.goal);
      choice.querySelector('[data-player-bar]').style.width = Math.min(100, player.progress || 0) + '%';
    }
    renderPlayer();
    document.dispatchEvent(new CustomEvent('hub:round-data', {detail: data.item_version}));
  }

  async function load() {
    if (!root.dataset.live || busy || authLost || document.hidden || (view !== 'players' && !(launch && view === 'play'))) return;
    busy = true;
    try {
      const response = await fetch(root.dataset.live, {cache: 'no-store'});
      const data = await response.json();
      if (response.status === 401) {
        authLost = true;
        window.HUB_AUTH_REQUIRED?.(data.login_url);
      }
      if (!response.ok) throw new Error(data.error || t('Die Anfrage konnte nicht abgeschlossen werden.'));
      render(data);
    } catch (error) {
      if (liveStatus) liveStatus.textContent = error.message;
    } finally {
      busy = false;
    }
  }

  async function poll() {
    await load();
    if (!authLost && (root.dataset.phase !== 'completed' || !playerStates.size)) setTimeout(poll, 8000);
  }
  selectPlayer(selected);
  openView();
  if (root.dataset.live) setTimeout(poll, 8000);
})();
