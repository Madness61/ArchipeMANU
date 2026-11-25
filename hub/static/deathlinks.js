(() => {
  "use strict";
  const root = document.getElementById("live-deathlinks");
  if (!root) return;
  const $ = id => document.getElementById(id);
  const t = window.HUB_I18N.t;
  const count = n => new Intl.NumberFormat(window.HUB_I18N.locale).format(n);
  const date = seconds => new Date(seconds * 1000).toLocaleString(window.HUB_I18N.locale);
  const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text; return n; };
  let timer, inflight = false, stopped = false;
  function render(data) {
    $("deathlink-total").textContent = data.total == null ? "—" : count(data.total);
    const status = data.state === "race" ? t("Im Race-Modus ist die DeathLink-Aufzeichnung deaktiviert.")
      : data.state === "completed" ? t("Aufzeichnung abgeschlossen.")
      : data.state === "recording" ? t("DeathLink-Aufzeichnung aktiv.")
      : t("DeathLink-Aufzeichnung derzeit nicht verbunden. Während dieser Zeit können Ereignisse fehlen.");
    $("deathlink-status").textContent = status + (data.since ? " " + t("Aufzeichnung seit {v0}.", {v0:date(data.since)}) : "")
      + (data.invalid_events ? " " + t("Ungültige DeathLink-Pakete wurden verworfen: {v0}.", {v0:count(data.invalid_events)}) : "");
    $("deathlink-ranking").replaceChildren(...data.ranking.map(row => {
      const li = node("li", ""), label = node("div", ""); label.className = "ranking-label";
      label.append(node("span", row.slot), node("strong", count(row.count))); li.append(label); return li;
    }));
    if (!data.ranking.length) $("deathlink-ranking").append(node("li", t("Noch keine eindeutig zugeordneten DeathLinks aufgezeichnet.")));
    $("deathlink-unresolved").hidden = !data.unresolved.length;
    $("deathlink-unresolved-list").replaceChildren(...data.unresolved.map(row => node("li", row.source + " · " + count(row.count))));
    $("deathlink-history").replaceChildren(...data.recent.map(row => {
      const li = node("li", ""), stamp = node("time", date(row.death_time));
      stamp.dateTime = new Date(row.death_time * 1000).toISOString();
      li.append(stamp, node("strong", row.slot || row.source));
      if (!row.slot) { const label = node("span", t("Nicht eindeutig zugeordnet")); label.className = "small muted"; li.append(label); }
      if (row.slot && row.slot !== row.source) li.append(node("span", row.source));
      if (row.cause) li.append(node("p", row.cause));
      return li;
    }));
    if (!data.recent.length) $("deathlink-history").append(node("li", t("Noch keine DeathLinks beobachtet. Ohne DeathLink-fähige, aktivierte Spielclients bleibt diese Ansicht leer. Ob DeathLink unterstützt wird, lässt sich daraus nicht erkennen.")));
    $("deathlink-gaps").hidden = !data.gaps.length;
    $("deathlink-gap-count").textContent = count(data.gap_count || 0);
    $("deathlink-gap-list").replaceChildren(...data.gaps.map(gap => node("li", date(gap.start) + " – " + (gap.end ? date(gap.end) : t("bis jetzt")))));
    if (data.state === "completed" || data.state === "race") stopped = true;
  }
  async function load() {
    if (inflight || document.hidden) return;
    clearTimeout(timer); inflight = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(root.dataset.url, {cache:"no-store", signal:controller.signal});
      if (!response.ok) throw new Error();
      render(await response.json());
    } catch {
      $("deathlink-status").textContent = t("DeathLink-Daten derzeit nicht erreichbar. Angezeigte Werte können veraltet sein.");
    } finally {
      clearTimeout(timeout); inflight = false;
      if (!stopped) timer = setTimeout(load, 5000);
    }
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !stopped) load(); });
  window.addEventListener("pagehide", () => clearTimeout(timer));
  load();
})();
