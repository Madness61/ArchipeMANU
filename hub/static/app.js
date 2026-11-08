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

  $$("[data-copy]").forEach(button => button.addEventListener("click", () => {
    const target = document.querySelector(button.dataset.copy);
    if (!target) return;
    const value = target.textContent.trim();
    if (navigator.clipboard) {
      navigator.clipboard.writeText(value).then(() => { button.textContent = "Kopiert"; });
    } else {
      button.title = value;
    }
  }));

  // Confirm dialogs for destructive forms.
  $$("form[data-confirm]").forEach((form) =>
    form.addEventListener("submit", (e) => { if (!confirm(form.dataset.confirm)) e.preventDefault(); }));

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
  const label = (t) => (t.is_default ? "★ " : "") + t.name + " · " + t.source;
  const templateOption = (t) => {
    const option = new Option(label(t) + (t.compatible === false ? " (inkompatibel)" : ""), t.ref);
    option.disabled = t.compatible === false;
    return option;
  };

  const addGame = document.getElementById("add-game");
  const addRef = document.getElementById("add-ref");
  if (addGame && addRef) {
    let templateRequest = 0;
    addGame.addEventListener("change", () => {
      const currentRequest = ++templateRequest;
      const slug = addGame.value;
      const editor = document.getElementById("selection-editor");
      if (editor) editor.hidden = true;
      addRef.replaceChildren(new Option("Gruppen-Standard", ""));
      if (!slug) return;
      templatesFor(slug).then((list) => {
        if (currentRequest === templateRequest && addGame.value === slug) {
          list.forEach((t) => addRef.add(templateOption(t)));
        }
      }).catch(() => { addRef.title = "Vorlagen konnten nicht geladen werden. Die Auswahl funktioniert auch mit dem Gruppen-Standard."; });
    });
    addRef.addEventListener("change", () => {
      const editor = document.getElementById("selection-editor");
      if (editor) editor.hidden = true;
    });
  }

  $$("select.entry-ref").forEach((sel) => {
    sel.addEventListener("focus", () => templatesFor(sel.dataset.game).then((list) => {
      list.forEach((t) => { if (t.ref !== sel.dataset.current) sel.add(templateOption(t)); });
    }), { once: true });
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
