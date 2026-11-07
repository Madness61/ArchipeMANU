// Small progressive enhancements; every page works without JS except the name pickers.
(function () {
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

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

  const addGame = document.getElementById("add-game");
  const addRef = document.getElementById("add-ref");
  if (addGame && addRef) {
    addGame.addEventListener("change", () => {
      addRef.replaceChildren(new Option("Gruppen-Standard", ""));
      if (!addGame.value) return;
      templatesFor(addGame.value).then((list) => list.forEach((t) => addRef.add(new Option(label(t), t.ref))));
    });
  }

  $$("select.entry-ref").forEach((sel) => {
    sel.addEventListener("focus", () => templatesFor(sel.dataset.game).then((list) => {
      list.forEach((t) => { if (t.ref !== sel.dataset.current) sel.add(new Option(label(t), t.ref)); });
    }), { once: true });
    sel.addEventListener("change", () => { if (sel.value !== sel.dataset.current) sel.form.submit(); });
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
})();
