// Small progressive enhancements; every page works without JS except the name pickers.
(function () {
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  // Never replace a page with an English 401 or silently discard an open composer.
  window.HUB_AUTH_REQUIRED = loginUrl => {
    const notice=document.getElementById('auth-required'),link=document.getElementById('auth-required-link');
    if(!notice||!link)return;
    const target=new URL(loginUrl||'/login',location.origin);
    if(target.origin!==location.origin||target.pathname!=='/login')return;
    link.href=target.href;notice.classList.add('flash','warn');notice.hidden=false;
  };

  // One navigation drawer on small screens, with keyboard focus containment.
  const menuToggle = document.getElementById("menu-toggle");
  const menuPanel = document.getElementById("sidebar-body");
  const scrim = document.getElementById("nav-scrim");
  const main = document.getElementById("main-content");
  const mobile = matchMedia("(max-width: 900px)");
  const setMenu = (open, restore = false) => {
    if (!menuToggle) return;
    const active = open && mobile.matches;
    document.body.classList.toggle("menu-open", active);
    menuToggle.setAttribute("aria-expanded", String(active));
    menuToggle.setAttribute("aria-label", active ? "Menü schließen" : "Menü öffnen");
    menuToggle.querySelector("use").setAttribute("href", menuToggle.querySelector("use").getAttribute("href").replace(/#[^#]+$/, active ? "#close" : "#menu"));
    scrim.hidden = !active;
    main.inert = active;
    if (restore) menuToggle.focus();
  };
  menuToggle?.addEventListener("click", () => setMenu(menuToggle.getAttribute("aria-expanded") !== "true"));
  scrim?.addEventListener("click", () => setMenu(false, true));
  mobile.addEventListener("change", () => setMenu(false));
  document.addEventListener("keydown", event => {
    if (!document.body.classList.contains("menu-open")) return;
    if (event.key === "Escape") { event.preventDefault(); setMenu(false, true); }
    if (event.key !== "Tab") return;
    const controls = $$("a[href],button,input:not([type=hidden])", document.querySelector("header.top")).filter(n => n.getClientRects().length && !n.disabled);
    if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1).focus(); }
    else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0].focus(); }
  });
  document.addEventListener("click", event => {
    if (event.target.closest("#sidebar-body a") && mobile.matches) setMenu(false);
  });

  // Option search only hides controls; it never removes/disables submitted values.
  $$("[data-option-editor]").forEach(editor => {
    const search = editor.querySelector("[data-option-search]");
    if (!search) return;
    const options = $$(".opt", editor), groups = $$("details.group", editor);
    const starts = new Map(options.map(option => [option, JSON.stringify($$("input,select,textarea", option).filter(n => n.name && n.name !== "_r").map(n => [n.name,n.value,n.checked]))]));
    const openStates = new Map();
    const updateChanges = () => {
      const changed = options.filter(option => {
        const edited = starts.get(option) !== JSON.stringify($$("input,select,textarea", option).filter(n => n.name && n.name !== "_r").map(n => [n.name,n.value,n.checked]));
        option.classList.toggle("is-edited", edited);
        let flag = option.querySelector(".edit-flag");
        if (edited && !flag) { flag = document.createElement("span"); flag.className = "chip edit-flag"; flag.setAttribute("aria-hidden", "true"); flag.textContent = "Bearbeitet"; option.querySelector("label.name").append(flag); }
        if (flag) flag.hidden = !edited;
        return edited || option.classList.contains("changed");
      });
      const list = editor.querySelector("[data-option-changes]");
      list.replaceChildren();
      changed.forEach(option => {
        const item = document.createElement("li"), name = document.createElement("strong");
        name.textContent = option.dataset.optionName;
        const field = option.querySelector("[id^='f-']");
        const current = field?.type === "checkbox" ? (field.checked ? "An" : "Aus") : field?.value || "Komplexer Wert";
        item.append(name, document.createTextNode(" · " + current.slice(0,120)));
        list.append(item);
      });
      editor.querySelector("[data-change-count]").textContent = String(changed.length);
      if (!changed.length) { const item = document.createElement("li"); item.textContent = "Keine angepassten Werte."; list.append(item); }
    };
    const filterOptions = () => {
      const query = search.value.toLocaleLowerCase("de").trim();
      let count = 0;
      options.forEach(option => {
        const visible = !query || option.textContent.toLocaleLowerCase("de").includes(query) || option.dataset.optionKey.includes(query);
        option.hidden = !visible; if (visible) count++;
      });
      groups.forEach(group => {
        if (query && !openStates.has(group)) openStates.set(group, group.open);
        group.hidden = !$$(".opt",group).some(option => !option.hidden);
        if (query && !group.hidden) group.open = true;
        if (!query && openStates.has(group)) { group.open = openStates.get(group); openStates.delete(group); }
      });
      editor.querySelector("[data-option-count]").textContent = count + " von " + options.length + " Optionen";
      editor.querySelector("[data-options-empty]").hidden = count > 0;
    };
    search.addEventListener("input", filterOptions);
    editor.querySelector("[data-option-search-clear]").addEventListener("click", () => { search.value = ""; filterOptions(); search.focus(); });
    editor.addEventListener("input", updateChanges);
    editor.addEventListener("change", updateChanges);
    filterOptions(); updateChanges();
  });

  // All cards are present so filtering never reloads the page or loses input focus.
  const chooseGame = document.getElementById("add-game");
  const updateGamePreview = () => {
    if (!chooseGame) return;
    const selected = chooseGame.selectedOptions[0];
    const title = document.querySelector("[data-chosen-game-name]");
    if (title) title.textContent = chooseGame.value ? selected.textContent : "Welche Welt wird deine?";
    const art = document.querySelector(".selection-art .game-art");
    if (art && selected?.dataset.hue) art.style.setProperty("--game-hue", selected.dataset.hue);
    document.querySelectorAll("[data-choose-game]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.chooseGame === chooseGame.value)));
  };
  chooseGame?.addEventListener("change", updateGamePreview);
  document.querySelectorAll("[data-choose-game]").forEach(button => button.addEventListener("click", () => {
    chooseGame.value = button.dataset.chooseGame;
    chooseGame.dispatchEvent(new Event("change", {bubbles:true}));
    button.closest("details").open = false;
    chooseGame.focus();
  }));
  document.querySelector("[data-game-search]")?.addEventListener("input", event => {
    let count = 0;
    document.querySelectorAll("[data-choose-game]").forEach(button => {
      button.hidden = !button.textContent.toLowerCase().includes(event.target.value.toLowerCase().trim());
      if (!button.hidden) count++;
    });
    document.querySelector("[data-game-empty]").hidden = count > 0;
  });
  updateGamePreview();
  const libraryFilters = document.getElementById("library-filters");
  if (libraryFilters) {
    const cards = $$("[data-library-game]").map(card => ({
      card, search: card.dataset.search, kind: card.dataset.kind,
      state: card.dataset.state, genres: JSON.parse(card.dataset.genres), tags: JSON.parse(card.dataset.tags), setup: card.dataset.setup,
    }));
    const fields = ["q", "kind", "state", "genre", "tag", "setup"];
    const filter = (updateUrl = true) => {
      const values = Object.fromEntries(fields.map(name => [name, libraryFilters.elements[name].value]));
      const query = values.q.trim().toLowerCase();
      let count = 0;
      cards.forEach(item => {
        const visible = item.search.includes(query)
          && (values.kind === "all" || values.kind === item.kind)
          && (values.state === "all" || values.state === item.state || (values.state === "unloaded" && item.state !== "loaded"))
          && (values.genre === "all" || item.genres.includes(values.genre))
          && (values.tag === "all" || item.tags.includes(values.tag))
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
      if (!page.getElementById("round-center") && !page.getElementById("participants-section")) throw new Error("Session unavailable");
      const drafts = $$("form[data-preserve-draft][data-dirty='1']").map(form => ({
        id: form.id,
        fields: $$("input,select,textarea", form).filter(field => field.name !== "_csrf").map(field => ({
          name: field.name, value: field.value, checked: field.checked,
        })),
      }));
      const currentRound = document.getElementById("round-center"), nextRound = page.getElementById("round-center");
      if (currentRound && nextRound && (currentRound.dataset.phase !== nextRound.dataset.phase || currentRound.dataset.buildStatus !== nextRound.dataset.buildStatus)) {
        if (drafts.length) {
          status.textContent = "Der Rundenstatus hat sich geändert. Deine Eingaben bleiben hier erhalten. Öffne die Runde erneut, um den neuen Stand zu sehen.";
          return;
        }
        history.replaceState(null, "", response.url + "#play");
        location.reload();
        return;
      }
      if (currentRound && nextRound) Object.assign(currentRound.dataset, nextRound.dataset);
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
          more.textContent = "Weitere Werte siehst du unter „Einstellungen anpassen“.";
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
