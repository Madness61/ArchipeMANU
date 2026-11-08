// Small progressive enhancements; every page works without JS except the name pickers.
(function () {
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // All cards are present so filtering never reloads the page or loses input focus.
  const libraryFilters = document.getElementById("library-filters");
  if (libraryFilters) {
    const cards = $$("[data-library-game]").map(card => ({
      card, search: card.dataset.search, kind: card.dataset.kind,
      state: card.dataset.state, genres: JSON.parse(card.dataset.genres), setup: card.dataset.setup,
    }));
    const fields = ["q", "kind", "state", "genre", "setup"];
    const filter = (updateUrl = true) => {
      const values = Object.fromEntries(fields.map(name => [name, libraryFilters.elements[name].value]));
      const query = values.q.trim().toLowerCase();
      let count = 0;
      cards.forEach(item => {
        const visible = item.search.includes(query)
          && (values.kind === "all" || values.kind === item.kind)
          && (values.state === "all" || values.state === item.state || (values.state === "unloaded" && item.state !== "loaded"))
          && (values.genre === "all" || item.genres.includes(values.genre))
          && (values.setup === "all" || values.setup === item.setup);
        item.card.hidden = !visible;
        if (visible) count++;
      });
      document.getElementById("library-count").textContent = `${count} von ${cards.length} Spielen`;
      document.getElementById("library-empty").hidden = count > 0;
      if (updateUrl) {
        const url = new URL(location.href);
        fields.forEach(name => {
          if (!values[name] || values[name] === "all") url.searchParams.delete(name);
          else url.searchParams.set(name, values[name]);
        });
        history.replaceState(null, "", url);
      }
    };
    libraryFilters.addEventListener("input", () => filter());
    libraryFilters.addEventListener("change", () => filter());
    libraryFilters.addEventListener("submit", event => { event.preventDefault(); filter(); });
    $$("[data-filter-reset]").forEach(link => link.addEventListener("click", event => {
      event.preventDefault();
      fields.forEach(name => { libraryFilters.elements[name].value = name === "q" ? "" : "all"; });
      filter();
      libraryFilters.elements.q.focus();
    }));
    window.addEventListener("popstate", () => {
      const params = new URL(location.href).searchParams;
      fields.forEach(name => {
        let value = params.get(name) || (name === "q" ? "" : "all");
        if (name === "state") value = ({ready: "loaded", pending: "unloaded"})[value] || value;
        libraryFilters.elements[name].value = value;
      });
      filter(false);
    });
    libraryFilters.querySelector("[data-filter-submit]").hidden = true;
    libraryFilters.querySelector(".live-filter-hint").hidden = false;
    filter(false);
  }

  document.addEventListener("click", event => {
    const button = event.target.closest("[data-copy]");
    if (!button) return;
    const target = document.querySelector(button.dataset.copy);
    if (!target) return;
    const value = target.textContent.trim();
    if (navigator.clipboard) {
      navigator.clipboard.writeText(value).then(() => { button.textContent = "Kopiert"; });
    } else {
      button.title = value;
    }
  });

  // Confirm dialogs for destructive forms.
  document.addEventListener("submit", event => {
    const form = event.target.closest("form[data-confirm]");
    if (form && !confirm(form.dataset.confirm)) event.preventDefault();
  });

  // Refresh lobby status without throwing away an open YAML or hosting draft.
  let sessionRefreshing = false;
  document.addEventListener("input", event => {
    const form = event.target.closest("form[data-preserve-draft]");
    if (form) form.dataset.dirty = "1";
  });
  document.addEventListener("change", event => {
    const form = event.target.closest("form[data-preserve-draft]");
    if (form) form.dataset.dirty = "1";
  });
  document.addEventListener("click", async event => {
    const button = event.target.closest("[data-session-refresh]");
    if (!button) return;
    event.preventDefault();
    if (sessionRefreshing) return;
    sessionRefreshing = true;
    const status = document.getElementById("session-refresh-status");
    const participants = document.getElementById("participants-section");
    status.textContent = "Teilnehmer und generierte Runden werden aktualisiert …";
    participants?.setAttribute("aria-busy", "true");
    button.setAttribute("aria-disabled", "true");
    try {
      const response = await fetch(button.href, {cache: "no-store", headers: {"Accept": "text/html"}});
      if (!response.ok) throw new Error("Refresh failed");
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      if (!page.getElementById("participants-section")) throw new Error("Session unavailable");
      const drafts = $$("form[data-preserve-draft][data-dirty='1']").map(form => ({
        id: form.id,
        fields: $$("input,select,textarea", form).filter(field => field.name !== "_csrf").map(field => ({
          name: field.name, value: field.value, checked: field.checked,
        })),
      }));
      $$("[data-refresh-fragment], #main-navigation").forEach(fragment => {
        const updated = page.getElementById(fragment.id);
        if (updated) fragment.replaceWith(updated);
      });
      drafts.forEach(draft => {
        const form = document.getElementById(draft.id);
        if (!form) return;
        form.dataset.dirty = "1";
        draft.fields.forEach(saved => {
          const field = form.elements.namedItem(saved.name);
          if (field) { field.value = saved.value; if (typeof saved.checked === "boolean") field.checked = saved.checked; }
        });
      });
      status.textContent = "Teilnehmer und generierte Runden wurden aktualisiert.";
    } catch {
      status.textContent = "Aktualisierung fehlgeschlagen. Bitte erneut versuchen oder neu anmelden. Deine Eingaben bleiben erhalten.";
    } finally {
      document.getElementById("participants-section")?.removeAttribute("aria-busy");
      document.querySelectorAll("[data-session-refresh]").forEach(link => link.removeAttribute("aria-disabled"));
      sessionRefreshing = false;
    }
  });

  // Option docs: click to expand.
  $$(".opt .doc").forEach((el) => el.addEventListener("click", () => el.classList.toggle("open")));

  // Fetch a progression item's exact checks only after an explicit reveal.
  $$("details[data-progression-url]").forEach((details) => {
    let loaded = false;
    let loading = false;
    details.addEventListener("toggle", async () => {
      if (!details.open || loaded || loading) return;
      const target = details.querySelector(".progression-world");
      const fallback = details.querySelector(".progression-fallback");
      loading = true;
      target.textContent = "Fundorte werden geladen …";
      try {
        const response = await fetch(details.dataset.progressionUrl, { headers: { "Accept": "application/json" }, cache: "no-store" });
        if (!response.ok) throw new Error("Reveal failed");
        const data = await response.json();
        const list = document.createElement("ul");
        data.worlds.forEach((world) => {
          world.locations.forEach((location) => {
            const item = document.createElement("li");
            item.textContent = `${location.name} — ${world.name} · ${world.game}`;
            list.append(item);
          });
        });
        target.replaceChildren(list);
        fallback.hidden = true;
        loaded = true;
      } catch {
        target.textContent = "Fundorte konnten nicht geladen werden. Erneut aufklappen oder den Link unten verwenden.";
      } finally {
        loading = false;
      }
    });
  });

  // Range slider <-> number field.
  $$("input[type=range][data-sync]").forEach((slider) => {
    const field = document.getElementById(slider.dataset.sync);
    slider.addEventListener("input", () => { field.value = slider.value; });
    field.addEventListener("input", () => { if (/^-?\d+$/.test(field.value)) slider.value = field.value; });
  });
  $$("select[data-set]").forEach((sel) => sel.addEventListener("change", () => {
    if (!sel.value) return;
    const field = document.getElementById(sel.dataset.set);
    field.value = sel.value;
    field.dispatchEvent(new Event("input"));
    sel.value = "";
  }));

  // Item/location name pickers for list-style options.
  let namesPromise = null;
  const loadNames = () => (namesPromise ??= fetch(window.HUB_NAMES_URL).then((r) => r.json()));
  $$(".name-picker").forEach((input, i) => {
    const list = document.createElement("datalist");
    list.id = "names-" + i;
    input.setAttribute("list", list.id);
    input.after(list);
    const fill = (names) => { list.replaceChildren(...names.map((n) => new Option(n))); };
    if (input.dataset.keys) fill(input.dataset.keys.split("\n").filter(Boolean));
    else if (input.dataset.source) input.addEventListener("focus", () => loadNames().then((d) => fill(d[input.dataset.source])), { once: true });

    const add = () => {
      const name = input.value.trim();
      if (!name) return;
      const target = document.getElementById(input.dataset.target);
      const line = input.dataset.counter === "1" ? name + ": 1" : name;
      target.value = (target.value.trim() ? target.value.trimEnd() + "\n" : "") + line;
      input.value = "";
    };
    input.nextElementSibling.nextElementSibling?.addEventListener("click", add);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  });

  // Session page: template dropdowns depend on the chosen game.
  const templatesFor = (slug) => fetch(window.HUB_TEMPLATES_URL.replace("__SLUG__", encodeURIComponent(slug))).then((r) => r.json());
  const label = (t) => (t.is_default ? "★ " : "") + t.name + " · " + (t.ref === "default" ? "Spielvorgaben" : t.source)
    + (t.summary?.length ? ` · ${t.summary.length} Änderungen` : "");
  const templateOption = (t) => {
    const option = new Option(label(t) + (t.compatible === false ? " (inkompatibel)" : ""), t.ref);
    option.disabled = t.compatible === false;
    return option;
  };

  const addGame = document.getElementById("add-game");
  const addRef = document.getElementById("add-ref");
  if (addGame && addRef) {
    let templateRequest = 0;
    let currentTemplates = null;
    const explainTemplate = () => {
      const list = currentTemplates || window.HUB_SELECTION_TEMPLATES || [];
      const selected = list.find(t => t.ref === addRef.value) || (addRef.value === "" ? list.find(t => t.is_default) : null);
      const target = document.getElementById("template-explanation");
      if (!target) return;
      const baseButton = document.getElementById("use-base-values");
      baseButton.textContent = selected && selected.ref !== "default" ? "Vorlage übernehmen" : "Standardwerte übernehmen";
      if (!selected) {
        target.textContent = addGame.value ? "Die Standardauswahl wird beim Übernehmen geprüft." : "Wähle ein Spiel, um seine Grundeinstellungen zu sehen.";
        return;
      }
      const title = document.createElement("strong");
      title.textContent = selected.name;
      const description = document.createElement("p");
      description.className = "small";
      description.textContent = selected.description;
      target.replaceChildren(title, description);
      if (selected.summary?.length) {
        const heading = document.createElement("p");
        heading.className = "small muted";
        heading.textContent = `${selected.summary.length} Abweichungen vom Spiel-Standard:`;
        const summary = document.createElement("ul");
        summary.className = "summary";
        selected.summary.slice(0, 6).forEach(([name, value]) => {
          const item = document.createElement("li");
          item.textContent = `${name}: ${value}`;
          summary.append(item);
        });
        target.append(heading, summary);
        if (selected.summary.length > 6) {
          const more = document.createElement("p");
          more.className = "small muted";
          more.textContent = "Weitere Werte siehst du unter „YAML überarbeiten“.";
          target.append(more);
        }
      }
    };
    addGame.addEventListener("change", () => {
      const currentRequest = ++templateRequest;
      const slug = addGame.value;
      const editor = document.getElementById("selection-editor");
      if (editor) editor.hidden = true;
      currentTemplates = [];
      addRef.replaceChildren(new Option("Standardauswahl der Gruppe", ""));
      explainTemplate();
      if (!slug) return;
      templatesFor(slug).then((list) => {
        if (currentRequest === templateRequest && addGame.value === slug) {
          list.forEach((t) => addRef.add(templateOption(t)));
          currentTemplates = list;
          explainTemplate();
        }
      }).catch(() => { addRef.title = "Vorlagen konnten nicht geladen werden. Die Auswahl funktioniert auch mit dem Gruppen-Standard."; });
    });
    addRef.addEventListener("change", () => {
      const editor = document.getElementById("selection-editor");
      if (editor) editor.hidden = true;
      explainTemplate();
    });
  }

  // Changing a field never requires opting in to inheritance; reset is optional.
  const showOptionReset = event => {
    const reset = event.target.closest(".opt")?.querySelector("[data-option-reset]");
    if (reset) reset.hidden = false;
  };
  document.addEventListener("input", showOptionReset);
  document.addEventListener("change", showOptionReset);

  document.addEventListener("focusin", event => {
    const sel = event.target.closest("select.entry-ref");
    if (!sel || sel.dataset.loaded) return;
    sel.dataset.loaded = "1";
    templatesFor(sel.dataset.game).then(list => {
      list.forEach(t => { if (t.ref !== sel.dataset.current) sel.add(templateOption(t)); });
    }).catch(() => { delete sel.dataset.loaded; });
  });

  // New builds are recorded independently from previous generations.
  if (document.querySelector('[data-build-status="queued"], [data-build-status="running"]')) {
    setTimeout(() => location.reload(), 4000);
  }

  // Poll while something runs on the server, then reload.
  const poll = (el, url) => {
    if (!el || !["queued", "running"].includes(el.dataset.status)) return;
    const tick = () => fetch(url).then((r) => r.json()).then((d) => {
      if (!["queued", "running"].includes(d.status)) location.reload(); else setTimeout(tick, 3000);
    }).catch(() => setTimeout(tick, 5000));
    setTimeout(tick, 3000);
  };
  const gen = document.getElementById("gen");
  poll(gen, gen?.dataset.statusUrl);
  const ext = document.getElementById("extract-status");
  poll(ext, ext?.dataset.url);
  const worldExtract = document.getElementById("world-extract-status");
  if (!ext) poll(worldExtract, worldExtract?.dataset.url);
})();
