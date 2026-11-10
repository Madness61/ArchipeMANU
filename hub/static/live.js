(() => {
  "use strict";
  const root = document.getElementById("live-dashboard");
  if (!root) return;
  const $ = id => document.getElementById(id);
  const fmt = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
  const colors = ["#A89CFF", "#5EE3B1", "#F5BC79", "#EFA2C3", "#85B6F4", "#D8BE91", "#A0D28D", "#C9A2EF"];
  const value = n => n == null ? "Nicht verfügbar" : fmt.format(n);
  const pct = n => n == null ? "Nicht verfügbar" : value(n) + " %";
  const date = (s, full = false) => s ? new Date(s).toLocaleString("de-DE", full
    ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }
    : { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "Nicht verfügbar";
  const set = (id, text) => { const el = $(id); if (el && el.textContent !== String(text)) el.textContent = text; };
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const svgNode = (tag, attributes = {}) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
  };
  let state = null, selectedPlayer = null, timer, inflight = false, lastChartStamp = "";
  const playerNodes = new Map(), overviewNodes = new Map(), charts = new Map();

  class Chart {
    constructor(container) {
      this.container = container;
      this.hidden = new Set();
      this.svg = svgNode("svg", { viewBox: "0 0 640 220", role: "img", "aria-label": "Gemessener Verlauf, Details über den Zeitregler darunter" });
      this.grid = svgNode("g");
      this.paths = svgNode("g");
      this.cursor = svgNode("line", { class: "chart-cursor", y1: 20, y2: 180, visibility: "hidden" });
      this.svg.append(this.grid, this.paths, this.cursor);
      this.tooltip = el("div", "", "chart-tooltip");
      this.tooltip.hidden = true;
      this.legend = el("div", null, "chart-legend");
      this.empty = el("p", "Ab dem ersten erfolgreichen Abruf erscheint hier der Verlauf.", "chart-empty");
      const label = el("label", "Zeitpunkt im Diagramm", "small muted");
      this.range = el("input", null, "chart-time-selector");
      this.range.type = "range"; this.range.min = "0"; this.range.step = "1";
      label.append(this.range);
      this.rangeLabel = label;
      container.append(this.empty, this.svg, this.legend, this.tooltip, label);
      this.svg.addEventListener("pointermove", event => {
        if (!this.points?.length) return;
        const bounds = this.svg.getBoundingClientRect();
        const target = (event.clientX - bounds.left) / bounds.width * (this.width || 640);
        let nearest = 0;
        this.points.forEach((p, i) => {
          if (Math.abs(this.x(i) - target) < Math.abs(this.x(nearest) - target)) nearest = i;
        });
        this.show(nearest);
      });
      this.svg.addEventListener("pointerleave", () => { this.tooltip.hidden = true; this.cursor.setAttribute("visibility", "hidden"); });
      this.range.addEventListener("input", () => this.show(Number(this.range.value)));
      this.range.addEventListener("blur", () => { this.tooltip.hidden = true; this.cursor.setAttribute("visibility", "hidden"); });
      this.resize = new ResizeObserver(entries => {
        if (entries[0].contentRect.width > 0 && this.points?.length) this.draw();
      });
      this.resize.observe(container);
    }
    update(points, series, percent = false, ceiling = null) {
      this.points = points; this.series = series; this.percent = percent; this.ceiling = ceiling;
      this.empty.hidden = points.length > 0;
      this.svg.hidden = !points.length; this.legend.hidden = !points.length; this.rangeLabel.hidden = !points.length;
      if (!points.length) return;
      this.range.max = String(points.length - 1);
      this.range.disabled = points.length === 1;
      const signature = series.map(s => s.key + ":" + s.label).join("|");
      if (this.signature !== signature) {
        this.legend.replaceChildren();
        series.forEach(series => {
          const button = el("button", series.label);
          button.type = "button"; button.style.setProperty("--series", series.color);
          button.setAttribute("aria-pressed", String(!this.hidden.has(series.key)));
          button.addEventListener("click", () => {
            if (this.hidden.has(series.key)) this.hidden.delete(series.key); else this.hidden.add(series.key);
            button.setAttribute("aria-pressed", String(!this.hidden.has(series.key)));
            this.draw();
          });
          this.legend.append(button);
        });
        this.signature = signature;
      }
      this.draw();
    }
    x(index) {
      const first = Date.parse(this.points[0].at), last = Date.parse(this.points.at(-1).at);
      const span = (this.width || 640) - 68;
      return last === first ? 48 + span / 2 : 48 + (Date.parse(this.points[index].at) - first) / (last - first) * span;
    }
    draw() {
      this.width = Math.max(320, Math.min(900, this.container.clientWidth || 640));
      this.svg.setAttribute("viewBox", "0 0 " + this.width + " 220");
      const active = this.series.filter(s => !this.hidden.has(s.key));
      let maximum = this.percent ? 100 : this.ceiling || 1;
      if (!this.percent) active.forEach(s => this.points.forEach(p => { maximum = Math.max(maximum, s.get(p) || 0); }));
      this.grid.replaceChildren(); this.paths.replaceChildren();
      for (let i = 0; i <= 4; i++) {
        const y = 180 - i * 40;
        this.grid.append(svgNode("line", { x1: 48, x2: this.width - 20, y1: y, y2: y, class: "chart-grid" }));
        const label = svgNode("text", { x: 40, y: y + 4, "text-anchor": "end" });
        label.textContent = value(maximum * i / 4) + (this.percent ? "%" : "");
        this.grid.append(label);
      }
      [0, this.points.length - 1].forEach((index, n) => {
        const label = svgNode("text", { x: n ? this.width - 20 : 48, y: 207, "text-anchor": n ? "end" : "start" });
        label.textContent = date(this.points[index].at, true);
        this.grid.append(label);
      });
      active.forEach(series => {
        let path = "", previous = null;
        this.points.forEach((point, index) => {
          const v = series.get(point);
          if (v == null) { previous = null; return; }
          const x = this.x(index), y = 180 - Math.min(maximum, Math.max(0, v)) / maximum * 160;
          path += (!previous || previous.segment !== point.segment ? "M" : "L") + x + "," + y + " ";
          previous = point;
          if (this.points.length === 1) this.paths.append(svgNode("circle", { cx: x, cy: y, r: 4, fill: series.color }));
        });
        this.paths.append(svgNode("path", { d: path, stroke: series.color, class: "chart-line" }));
      });
      if (!this.tooltip.hidden) this.show(Math.min(Number(this.range.value), this.points.length - 1));
    }
    show(index) {
      const point = this.points[index];
      if (!point) return;
      this.range.value = String(index);
      const lines = [date(point.at, true), ...this.series.filter(s => !this.hidden.has(s.key))
        .map(s => s.label + ": " + (this.percent ? pct(s.get(point)) : value(s.get(point))))];
      this.tooltip.textContent = lines.join("\n"); this.tooltip.hidden = false;
      this.cursor.setAttribute("x1", this.x(index)); this.cursor.setAttribute("x2", this.x(index));
      this.cursor.setAttribute("visibility", "visible");
      this.range.setAttribute("aria-valuetext", lines.join(", "));
    }
  }
  const chart = (id, points, series, percentage = false, ceiling = null) => {
    if (!charts.has(id)) charts.set(id, new Chart($(id)));
    charts.get(id).update(points, series, percentage, ceiling);
  };
  const seriesFor = players => players.map((p, i) => ({ key: p.key, label: p.name, color: colors[i % colors.length],
    get: point => point.players.find(v => v.key === p.key)?.progress ?? null }));

  function tab(name, changeHash = true) {
    if (!$("tab-" + name)) name = "overview";
    root.querySelectorAll("[role=tab]").forEach(button => {
      const selected = button.dataset.tab === name;
      button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1;
    });
    root.querySelectorAll("[role=tabpanel]").forEach(panel => { panel.hidden = panel.id !== "live-" + name; });
    if (changeHash) history.replaceState(null, "", "#live-" + name);
  }
  root.querySelectorAll("[data-tab]").forEach(button => {
    button.addEventListener("click", () => tab(button.dataset.tab));
    button.addEventListener("keydown", event => {
      const buttons = [...root.querySelectorAll("[data-tab]")], index = buttons.indexOf(button);
      const target = event.key === "ArrowRight" ? (index + 1) % buttons.length
        : event.key === "ArrowLeft" ? (index + buttons.length - 1) % buttons.length
        : event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : null;
      if (target != null) { event.preventDefault(); buttons[target].focus(); tab(buttons[target].dataset.tab); }
    });
  });
  root.querySelectorAll("[data-switch]").forEach(link => link.addEventListener("click", event => { event.preventDefault(); tab(link.dataset.switch); }));
  window.addEventListener("hashchange", () => tab(location.hash.replace("#live-", ""), false));
  tab(location.hash.replace("#live-", ""), false);

  function kpi(id, text) {
    const target = $("kpi-" + id);
    if (target.textContent === text) return;
    target.textContent = text;
    const card = target.closest("article");
    card.classList.remove("live-changed");
    requestAnimationFrame(() => card.classList.add("live-changed"));
  }
  function rankings(id, rows, format = value) {
    const container = $(id), known = rows.filter(row => row.value != null).sort((a, b) => b.value - a.value).slice(0, 12);
    container.replaceChildren();
    if (!known.length) { container.append(el("li", "Nicht verfügbar – noch keine ausreichenden Daten.", "muted small")); return; }
    const maximum = Math.max(1, ...known.map(row => row.value));
    known.forEach(row => {
      const li = el("li"), label = el("div", null, "ranking-label");
      label.append(el("span", row.name), el("strong", format(row.value)));
      const track = el("div", null, "ranking-track"), bar = el("span");
      bar.style.width = Math.max(0, row.value) / maximum * 100 + "%";
      bar.style.setProperty("--player", row.color || colors[0]);
      track.append(bar); li.append(label, track); container.append(li);
    });
  }
  function timeline(container, events, limit = 100) {
    const existing = new Map([...container.querySelectorAll("[data-event-id]")].map(node => [node.dataset.eventId, node]));
    if (!events.length) { container.replaceChildren(el("li", "Noch keine passenden Beobachtungen.", "muted")); return; }
    [...container.children].filter(node => !node.dataset.eventId).forEach(node => node.remove());
    const wanted = new Set();
    events.slice(0, limit).forEach(event => {
      const id = String(event.id); wanted.add(id);
      let item = existing.get(id);
      if (!item) {
        item = el("li"); item.dataset.eventId = id; item.dataset.kind = event.kind;
        const observed = el("time", "Beobachtet " + date(event.at, true) + (event.since ? " · seit " + date(event.since) : ""));
        observed.dateTime = event.at;
        item.append(el("span", event.text), observed);
      }
      container.append(item);
    });
    existing.forEach((node, id) => { if (!wanted.has(id)) node.remove(); });
  }
  function playerDetail(focus = false) {
    const player = state?.metrics?.players.find(p => p.key === selectedPlayer);
    $("live-player-detail").hidden = !player;
    if (!player) return;
    set("live-player-title", player.name + " · " + player.game);
    set("live-player-info", value(player.checks) + " / " + value(player.total) + " Checks · " + pct(player.progress)
      + " · " + value(player.received) + " empfangene Items · letzte Aktivität: " + date(player.activity, true));
    const series = seriesFor(state.metrics.players).find(s => s.key === player.key);
    chart("player-chart", state.history, [series], true);
    const categories = $("live-player-categories"); categories.replaceChildren();
    Object.entries({ progression: "Progression", useful: "Nützlich", trap: "Fallen", filler: "Füllitems" }).forEach(([field, label]) => {
      const box = el("div");
      box.append(el("span", label), el("strong", player.categories ? value(player.categories[field] || 0) : "—"));
      categories.append(box);
    });
    if (focus) { $("live-player-detail").focus({ preventScroll: true }); $("live-player-detail").scrollIntoView({ behavior: "smooth", block: "start" }); }
  }
  function players(data) {
    const overview = $("live-overview-players");
    const visibleKeys = new Set();
    data.players.slice(0, 6).forEach((player, i) => {
      visibleKeys.add(player.key);
      let card = overviewNodes.get(player.key);
      if (!card) {
        card = el("button", null, "overview-player"); card.type = "button";
        const progress = el("div", null, "overview-player-progress");
        progress.append(el("span"), el("span"));
        const track = el("div", null, "progress-track"); track.append(el("span"));
        card.append(el("strong"), el("small"), progress, track);
        card.addEventListener("click", () => { tab("players"); selectedPlayer = player.key; playerDetail(true); });
        overviewNodes.set(player.key, card); overview.append(card);
      }
      card.style.setProperty("--player", colors[i % colors.length]);
      card.querySelector("strong").textContent = player.name;
      card.querySelector("small").textContent = player.game;
      card.querySelector(".overview-player-progress>span").textContent = pct(player.progress);
      card.querySelector(".overview-player-progress>span:last-child").textContent = value(player.checks) + " Checks";
      card.querySelector(".progress-track>span").style.width = Math.min(100, player.progress || 0) + "%";
    });
    overviewNodes.forEach((node, id) => { if (!visibleKeys.has(id)) { node.remove(); overviewNodes.delete(id); } });
    const container = $("live-player-cards"), order = $("live-player-sort").value;
    const sorted = [...data.players].sort((a, b) => order === "slot" ? a.team - b.team || a.slot - b.slot
      : (b[order] ?? -1) - (a[order] ?? -1));
    if (!playerNodes.size) container.replaceChildren();
    const present = new Set();
    sorted.forEach(player => {
      present.add(player.key);
      let node = playerNodes.get(player.key);
      if (!node) {
        node = el("article", null, "panel live-player-card");
        node.dataset.player = player.key;
        const button = el("button", null, "player-title"); button.type = "button";
        button.addEventListener("click", () => { selectedPlayer = player.key; playerDetail(true); });
        const heading = el("h3"); heading.append(button);
        node.append(heading, el("p", null, "player-game"), el("div", null, "live-player-number"));
        const track = el("div", null, "live-progress-track"); track.append(el("span"));
        const spark = svgNode("svg", { viewBox: "0 0 250 45", class: "player-mini-chart", "aria-hidden": "true" });
        spark.append(svgNode("polyline"));
        node.append(track, spark, el("div", null, "player-card-meta"), el("p", null, "small muted player-activity"));
        playerNodes.set(player.key, node);
      }
      node.style.setProperty("--player", colors[data.players.findIndex(p => p.key === player.key) % colors.length]);
      node.querySelector("button").textContent = player.name + (data.players.some(p => p.team !== player.team) ? " · Team " + (player.team + 1) : "");
      node.querySelector(".player-game").textContent = player.game;
      node.querySelector(".live-player-number").replaceChildren(el("span", value(player.checks)), el("small", " / " + value(player.total) + " Checks"));
      node.querySelector(".live-progress-track>span").style.width = Math.min(100, player.progress || 0) + "%";
      node.querySelector(".player-card-meta").replaceChildren(el("span", pct(player.progress)), el("span", value(player.received) + " Items"),
        el("span", player.goal ? "✓ Ziel erreicht" : player.goal === false ? "Ziel noch offen" : "Zielstatus unbekannt"));
      node.querySelector(".player-activity").textContent = "Aktivität: " + date(player.activity, true);
      const segment = state.history.at(-1)?.segment;
      const points = state.history.filter(point => point.segment === segment).map(point => point.players.find(p => p.key === player.key)?.progress).filter(v => v != null);
      node.querySelector("polyline").setAttribute("points", points.map((n, i) => (points.length === 1 ? 125 : i / (points.length - 1) * 250) + "," + (42 - Math.min(100, n) / 100 * 39)).join(" "));
      node.querySelector(".player-mini-chart").hidden = points.length < 2;
      // Keep card nodes and focus; only reorder when necessary.
      const position = [...container.children].indexOf(node), expected = sorted.indexOf(player);
      if (position !== expected) container.insertBefore(node, container.children[expected] || null);
    });
    playerNodes.forEach((node, id) => { if (!present.has(id)) { node.remove(); playerNodes.delete(id); } });
    playerDetail();
  }
  function interactions(data) {
    const missing = data.interactions == null;
    const notice = $("live-interaction-notice");
    notice.hidden = !missing;
    notice.textContent = state.race ? "Race-Modus: Empfangsdetails und Beziehungen sind ausgeblendet." : "Keine verlässlich zugeordneten Empfangsdaten verfügbar.";
    set("live-foreign", value(data.foreign)); set("live-own", value(data.own));
    const unassigned = data.players.every(p => p.unattributed != null) ? data.players.reduce((n, p) => n + p.unattributed, 0) : null;
    set("live-unattributed", value(unassigned));
    const container = $("live-matrix");
    if (missing) { container.replaceChildren(el("p", "Keine Matrix verfügbar.", "muted")); return; }
    const signature = data.players.map(p => p.key).join("|");
    let table = container.querySelector("table");
    if (!table || table.dataset.signature !== signature) {
      table = el("table"); table.dataset.signature = signature;
      const head = el("thead"), row = el("tr"); row.append(el("th", "Finder ↓ / Empfänger →"));
      data.players.forEach(player => { const th = el("th", player.name); th.scope = "col"; row.append(th); });
      head.append(row); const body = el("tbody");
      data.players.forEach(finder => {
        const tr = el("tr"), th = el("th", finder.name); th.scope = "row"; tr.append(th);
        data.players.forEach(recipient => {
          const td = el("td"), button = el("button"); button.type = "button";
          button.dataset.edge = finder.key + "/" + recipient.key;
          td.append(button); tr.append(td);
        }); body.append(tr);
      }); table.append(head, body); container.replaceChildren(table);
    }
    const edges = new Map(data.interactions.map(e => [e.finder + "/" + e.recipient, e.count]));
    const maximum = Math.max(1, ...edges.values());
    table.querySelectorAll("[data-edge]").forEach(button => {
      const count = edges.get(button.dataset.edge) || 0, [finder, recipient] = button.dataset.edge.split("/");
      const label = data.players.find(p => p.key === finder).name + " → " + data.players.find(p => p.key === recipient).name + ": " + count + " zugeordnete Empfangsmeldungen";
      button.textContent = value(count); button.title = label; button.setAttribute("aria-label", label);
      button.style.setProperty("--heat", count ? .12 + .75 * count / maximum : .025); button.dataset.strong = String(count / maximum > .6);
    });
    rankings("live-help-ranking", data.players.map((p, i) => ({ name: p.name, value: p.sent_to_others, color: colors[i % colors.length] })));
  }
  function render(payload) {
    if (state && state.connection_id !== payload.connection_id) {
      ["checks", "progress", "players", "received", "goals", "games"].forEach(id => {
        kpi(id, "—"); set("kpi-" + id + "-detail", "Warte auf den neuen Raum.");
      });
      set("live-ring-label", "—"); $("live-ring").style.setProperty("--progress", "0%");
      $("live-total-bar").style.width = "0%";
      set("live-progress-caption", "Für den neu verbundenen Raum liegen noch keine Daten vor.");
      playerNodes.clear(); selectedPlayer = null;
      overviewNodes.clear(); $("live-overview-players").replaceChildren();
      $("live-player-cards").replaceChildren(el("p", "Warte auf die Spieler des neuen Raums.", "panel muted"));
      $("live-player-detail").hidden = true;
      charts.forEach(instance => { instance.hidden.clear(); instance.signature = null; instance.update([], []); });
      ["live-active-ranking", "live-help-ranking", "live-check-ranking", "live-progress-ranking", "live-gain-ranking", "live-game-ranking", "live-history-table"].forEach(id => $(id).replaceChildren());
      ["live-recent", "live-events-list"].forEach(id => timeline($(id), []));
      ["live-foreign", "live-own", "live-unattributed", "live-average", "live-spread", "live-goal-share"].forEach(id => set(id, "—"));
      $("live-matrix").replaceChildren(el("p", "Für den neuen Raum noch nicht verfügbar.", "muted"));
      set("live-history-caption", "Die Aufzeichnung dieses Raums beginnt mit seinem ersten erfolgreichen Abruf.");
      set("live-gain-caption", "Für den neuen Raum noch kein Vergleich verfügbar.");
      lastChartStamp = "";
    }
    state = payload;
    const data = payload.metrics;
    set("live-room-code", payload.room_id);
    $("live-room-link").href = payload.room_url;
    set("live-status-chip", payload.completed ? "Runde abgeschlossen" : payload.stale ? "Warte auf aktuellen Stand"
      : data && data.player_count > 0 && data.goals === data.player_count ? "Alle Spielziele gemeldet" : "Tracker verbunden");
    set("live-update", payload.updated_at ? "Letzter erfolgreicher Datenstand: " + date(payload.updated_at, true) : "Warte auf den ersten erfolgreichen Abruf …");
    set("live-next", payload.completed ? "Aufzeichnung abgeschlossen" : "Gemeinsame Aktualisierung alle 60 Sekunden");
    $("live-warning").hidden = !payload.error && !payload.stale;
    $("live-warning").textContent = payload.error
      ? payload.error + (data ? " Der letzte erfolgreiche Datenstand bleibt sichtbar." : " Es werden noch keine Werte angezeigt.")
      : payload.stale ? data ? "Der letzte erfolgreiche Stand ist älter als zwei Minuten. Er bleibt sichtbar, während neue Daten abgerufen werden."
        : "Der erste Tracker-Datenstand wird vorbereitet. Die Anzeige aktualisiert sich automatisch." : "";
    $("live-seed-warning").hidden = payload.seed_matches !== false;
    set("live-port", payload.room.port == null ? "Nicht verfügbar" : String(payload.room.port));
    set("live-room-activity", date(payload.room.last_activity, true));
    set("live-server-state", payload.room.port ? "Port gemeldet · Erreichbarkeit ungeprüft" : "Noch kein gültiger Port gemeldet");
    set("live-recording", payload.recording_since ? date(payload.recording_since, true) : "Noch kein erfolgreicher Abruf");
    $("live-tracker-link").hidden = !payload.tracker_id;
    if (payload.tracker_id) {
      $("live-tracker-link").href = "https://archipelago.gg/tracker/" + encodeURIComponent(payload.tracker_id);
    } else {
      $("live-tracker-link").removeAttribute("href");
    }
    if (!data) return;
    kpi("checks", data.checks == null ? "—" : value(data.checks));
    set("kpi-checks-detail", value(data.total) + " Gesamtchecks laut Tracker");
    kpi("progress", data.progress == null ? "—" : pct(data.progress));
    kpi("players", value(data.player_count)); kpi("games", value(data.games));
    set("kpi-progress-detail", "Erledigte Checks / Gesamtchecks");
    set("kpi-players-detail", "Individuelle Spielerslots, keine Gruppen");
    set("kpi-games-detail", "Spiele der verknüpften Multiworld");
    kpi("received", data.received == null ? "—" : value(data.received));
    set("kpi-received-detail", payload.race ? "Im Race-Modus ausgeblendet" : data.received == null ? "Nicht verfügbar" : "Empfangsliste des Servers, kein Spielinventar");
    kpi("goals", data.known_goals ? value(data.goals) + " / " + value(data.known_goals) : "—");
    set("kpi-goals-detail", data.known_goals === data.player_count ? "Alle Zielstatus verfügbar" : "Nur " + data.known_goals + " von " + data.player_count + " Zielstatus bekannt");
    set("live-ring-label", data.progress == null ? "—" : pct(data.progress));
    $("live-ring").style.setProperty("--progress", Math.min(100, data.progress || 0) + "%");
    $("live-total-bar").style.width = Math.min(100, data.progress || 0) + "%";
    set("live-progress-caption", value(data.checks) + " von " + value(data.total) + " Checks in " + data.games + " Spielen. " + data.goals + " gemeldete Spielziele erreicht.");
    if (data.progress > 100) { $("live-warning").hidden = false; $("live-warning").textContent = "Der Tracker meldet mehr Checks als die gespeicherten Gesamtzahlen. Statische Daten werden beim nächsten regulären Abruf geprüft."; }
    players(data); interactions(data);
    const filter = $("live-event-filter").value;
    timeline($("live-events-list"), payload.events.filter(e => filter === "all" || e.kind === filter));
    timeline($("live-recent"), payload.events, 4);
    const rowFor = field => data.players.map((p, i) => ({ name: p.name, value: p[field], color: colors[i % colors.length] }));
    rankings("live-check-ranking", rowFor("checks"));
    rankings("live-progress-ranking", rowFor("progress"), pct);
    rankings("live-gain-ranking", data.players.map((p, i) => ({ name: p.name, value: payload.gains[p.key], color: colors[i % colors.length] })));
    set("live-gain-caption", payload.gains_since ? "Seit " + date(payload.gains_since, true) + " · höchstens die aufgezeichnete letzte Stunde." : "Noch kein Vergleich verfügbar.");
    rankings("live-active-ranking", data.players.map((p, i) => {
      return { name: p.name, value: payload.recent_gains[p.key], color: colors[i % colors.length] };
    }));
    const games = new Map();
    data.players.forEach(p => {
      const prior = games.get(p.game);
      games.set(p.game, p.total == null || prior === null ? null : (prior || 0) + p.total);
    });
    rankings("live-game-ranking", [...games].map(([name, n]) => ({ name, value: n })));
    set("live-average", pct(data.average_progress));
    const progress = data.players.map(p => p.progress).filter(p => p != null);
    set("live-spread", progress.length === data.players.length ? value(Math.max(...progress) - Math.min(...progress)) + " Prozentpunkte" : "Nicht verfügbar");
    set("live-goal-share", data.known_goals === data.player_count ? pct(data.goals / data.player_count * 100) : "Nicht verfügbar");
    set("live-history-caption", (payload.recording_since ? "Aufzeichnung seit " + date(payload.recording_since, true) + ". " : "")
      + (payload.history_sampled ? "Ausgewählte echte Messpunkte für diesen Zeitraum." : "Nur tatsächlich beobachtete Datenstände.")
      + (payload.history.length < 2 ? " Weitere Abrufe ergänzen den Verlauf." : ""));
    const chartStamp = payload.connection_id + "/" + payload.updated_at + "/" + $("live-window").value;
    if (lastChartStamp !== chartStamp) {
      const total = [{ key: "total", label: "Multiworld-Fortschritt", color: colors[0], get: p => p.progress }];
      chart("overview-chart", payload.history, total, true);
      chart("history-chart", payload.history, seriesFor(data.players), true);
      const activity = payload.history.map((point, i) => {
        const before = payload.history[i - 1];
        return { ...point, delta: before && point.segment === before.segment && point.checks != null && before.checks != null ? Math.max(0, point.checks - before.checks) : null };
      });
      chart("activity-chart", activity, [{ key: "checks", label: "Neue Checks seit voriger Beobachtung", color: colors[1], get: p => p.delta }]);
      chart("goals-chart", payload.history, [{ key: "goals", label: "Erreichte Ziele", color: colors[2], get: p => p.known_goals ? p.goals : null }], false, data.player_count);
      const table = $("live-history-table"); table.replaceChildren();
      payload.history.forEach(point => {
        const tr = el("tr");
        [date(point.at, true), point.segment, value(point.checks), pct(point.progress), value(point.goals)].forEach(v => tr.append(el("td", v)));
        table.append(tr);
      });
      lastChartStamp = chartStamp;
    }
  }
  async function load(manual = false) {
    if (inflight || root.dataset.linked !== "1") return;
    clearTimeout(timer); inflight = true; $("live-refresh").disabled = true;
    $("live-refresh").textContent = "Wird aktualisiert …";
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const windowValue = $("live-window").value;
      const response = await fetch((manual ? root.dataset.refreshUrl : root.dataset.url) + "?window=" + encodeURIComponent(windowValue), {
        method: manual ? "POST" : "GET", credentials: "same-origin", cache: "no-store", signal: controller.signal,
        headers: { "Accept": "application/json", ...(manual ? { "X-CSRF-Token": root.dataset.csrf } : {}) },
      });
      if(response.status===401){const auth=await response.json().catch(()=>({}));window.HUB_AUTH_REQUIRED?.(auth.login_url);}
      if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? "Bitte erneut anmelden oder die Lobbyberechtigung prüfen." : "Der Datenstand konnte nicht geladen werden.");
      const payload = await response.json();
      render(payload);
    } catch (error) {
      $("live-warning").hidden = false;
      $("live-warning").textContent = (error.name === "AbortError" ? "Der Abruf dauert zu lange." : error.message) + (state?.metrics ? " Der letzte Datenstand bleibt sichtbar." : "");
      set("live-status-chip", "Verbindung unterbrochen");
    } finally {
      clearTimeout(timeout); inflight = false; $("live-refresh").disabled = false; $("live-refresh").textContent = "Jetzt aktualisieren";
      if (!state?.completed) timer = setTimeout(() => load(), state?.refresh_pending ? 1200 : state?.metrics ? 30000 : 5000);
    }
  }
  $("live-refresh")?.addEventListener("click", () => load(true));
  $("live-window")?.addEventListener("change", () => load());
  $("live-player-sort")?.addEventListener("change", () => { if (state?.metrics) players(state.metrics); });
  $("live-event-filter")?.addEventListener("change", () => { if (state) timeline($("live-events-list"), state.events.filter(e => $("live-event-filter").value === "all" || e.kind === $("live-event-filter").value)); });
  $("live-player-close")?.addEventListener("click", () => { selectedPlayer = null; $("live-player-detail").hidden = true; });
  $("live-present")?.addEventListener("click", async () => {
    const active = document.body.classList.toggle("live-presenting");
    $("live-present").setAttribute("aria-pressed", String(active));
    $("live-present").textContent = active ? "Präsentation beenden" : "Präsentationsmodus";
    if (active) {
      tab("overview");
      try { await document.documentElement.requestFullscreen?.(); } catch { /* CSS presentation also works without fullscreen. */ }
    } else if (document.fullscreenElement) { try { await document.exitFullscreen(); } catch { /* Optional browser feature. */ } }
  });
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) { document.body.classList.remove("live-presenting"); $("live-present").setAttribute("aria-pressed", "false"); $("live-present").textContent = "Präsentationsmodus"; }
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  window.addEventListener("pagehide", () => clearTimeout(timer));
  if (root.dataset.linked === "1") load();
})();
