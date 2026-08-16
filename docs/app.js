(() => {
  "use strict";

  const elements = {
    date: document.querySelector("#edition-date"),
    title: document.querySelector("#edition-title"),
    items: document.querySelector("#items"),
    status: document.querySelector("#status"),
    ending: document.querySelector("#ending"),
    fallback: document.querySelector("#fallback-note"),
    generated: document.querySelector("#generated-time"),
    template: document.querySelector("#card-template"),
    nav: document.querySelector("#archive-nav"),
    older: document.querySelector("#older-edition"),
    newer: document.querySelector("#newer-edition"),
    today: document.querySelector("#today-edition"),
    smaller: document.querySelector("#type-smaller"),
    reset: document.querySelector("#type-reset"),
    larger: document.querySelector("#type-larger"),
  };

  const typeSizes = [17, 19, 21, 23, 25];
  const defaultTypeIndex = 2;
  const storageKey = "morning-text-size";
  let typeIndex = readTypePreference();
  let archiveDates = [];
  let activeDate = null;

  function readTypePreference() {
    try {
      const stored = Number.parseInt(localStorage.getItem(storageKey), 10);
      return Number.isInteger(stored) && stored >= 0 && stored < typeSizes.length
        ? stored
        : defaultTypeIndex;
    } catch (_error) {
      return defaultTypeIndex;
    }
  }

  function applyTypeSize(index, announce = false) {
    typeIndex = Math.max(0, Math.min(typeSizes.length - 1, index));
    document.documentElement.style.setProperty("--reader-size", `${typeSizes[typeIndex]}px`);
    elements.smaller.disabled = typeIndex === 0;
    elements.larger.disabled = typeIndex === typeSizes.length - 1;
    elements.reset.setAttribute("aria-pressed", String(typeIndex === defaultTypeIndex));
    try {
      localStorage.setItem(storageKey, String(typeIndex));
    } catch (_error) {
      // The preference is a convenience; private browsing must not break reading.
    }
    if (announce) {
      showTransientStatus(`Text size ${typeSizes[typeIndex]} pixels.`);
    }
  }

  function showTransientStatus(message) {
    const announcer = document.createElement("span");
    announcer.className = "sr-only";
    announcer.setAttribute("role", "status");
    announcer.textContent = message;
    document.body.append(announcer);
    window.setTimeout(() => announcer.remove(), 1200);
  }

  function parseDate(value) {
    return new Date(`${value}T12:00:00`);
  }

  function longDate(value) {
    return new Intl.DateTimeFormat("en", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(parseDate(value));
  }

  function shortDate(value) {
    return new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(parseDate(value));
  }

  function itemDirection(item) {
    return item.language === "he" ? "rtl" : "ltr";
  }

  function addImage(card, copy, item) {
    if (!item.image) return;
    const figure = document.createElement("figure");
    figure.className = "card-media loading";
    const link = document.createElement("a");
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", `Open ${item.title}`);
    const image = document.createElement("img");
    image.src = item.image;
    image.alt = item.image_alt || "";
    image.loading = item.category === "astronomy" ? "eager" : "lazy";
    image.decoding = "async";
    image.referrerPolicy = "no-referrer";
    image.addEventListener("load", () => figure.classList.remove("loading"));
    image.addEventListener("error", () => figure.remove());
    link.append(image);
    figure.append(link);
    copy.insertBefore(figure, copy.querySelector(".card-footer"));
    card.classList.add("has-image");
  }

  function renderItem(item, index) {
    const fragment = elements.template.content.cloneNode(true);
    const card = fragment.querySelector(".card");
    const copy = fragment.querySelector(".card-copy");
    const label = fragment.querySelector(".card-label");
    const titleLink = fragment.querySelector(".card-title a");
    const summary = fragment.querySelector(".card-summary");
    const meta = fragment.querySelector(".card-meta");
    const read = fragment.querySelector(".read-link");

    card.dir = itemDirection(item);
    card.lang = item.language || "en";
    if (item.category === "astronomy" && index === 0) card.classList.add("featured");
    label.textContent = item.label || item.category || "Discovery";
    titleLink.textContent = item.title;
    titleLink.href = item.url;
    summary.textContent = item.summary;
    read.href = item.url;
    read.setAttribute("aria-label", `Read “${item.title}” at ${item.source}`);
    const details = [item.source];
    if (item.reading_minutes) details.push(`${item.reading_minutes} min read`);
    meta.textContent = details.filter(Boolean).join(" · ");
    addImage(card, copy, item);
    return fragment;
  }

  function renderEdition(edition) {
    activeDate = edition.date;
    elements.date.textContent = longDate(edition.date);
    elements.title.textContent = edition.items.length === 7
      ? "Seven interesting things for today."
      : `${edition.items.length} interesting things for today.`;
    elements.items.replaceChildren(...edition.items.map(renderItem));
    elements.status.hidden = true;
    elements.ending.hidden = false;
    elements.fallback.hidden = !edition.is_fallback;
    elements.generated.textContent = edition.generated_at
      ? `Edition assembled ${new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(edition.generated_at))}.`
      : "";
    document.title = `${longDate(edition.date)} — Morning`;
    updateArchiveControls();
  }

  function showError() {
    elements.status.innerHTML = "";
    const message = document.createElement("p");
    message.textContent = "This edition could not be opened. Check your connection, then try again.";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "Try again";
    retry.addEventListener("click", () => window.location.reload());
    elements.status.append(message, retry);
  }

  async function fetchJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function loadArchive() {
    try {
      const archive = await fetchJson("./data/archive.json");
      archiveDates = Array.isArray(archive.dates) ? archive.dates.sort().reverse() : [];
    } catch (_error) {
      archiveDates = [];
    }
  }

  async function loadEdition(requestedDate) {
    elements.status.hidden = false;
    elements.ending.hidden = true;
    elements.items.replaceChildren();
    elements.status.querySelector("span:last-child").textContent = "Opening the edition…";
    const path = requestedDate ? `./data/history/${requestedDate}.json` : "./data/today.json";
    try {
      const edition = await fetchJson(path);
      if (!edition || !Array.isArray(edition.items) || !edition.items.length) throw new Error("empty edition");
      renderEdition(edition);
      const url = new URL(window.location.href);
      if (requestedDate && requestedDate !== archiveDates[0]) url.searchParams.set("date", requestedDate);
      else url.searchParams.delete("date");
      window.history.replaceState({}, "", url);
    } catch (_error) {
      showError();
    }
  }

  function updateArchiveControls() {
    if (!archiveDates.length || !activeDate) {
      elements.nav.hidden = true;
      return;
    }
    if (!archiveDates.includes(activeDate)) archiveDates.push(activeDate);
    archiveDates.sort().reverse();
    const index = archiveDates.indexOf(activeDate);
    const older = archiveDates[index + 1];
    const newer = archiveDates[index - 1];
    elements.older.disabled = !older;
    elements.newer.disabled = !newer;
    elements.older.innerHTML = older ? `<span aria-hidden="true">←</span> ${shortDate(older)}` : "<span aria-hidden=\"true\">←</span> Previous";
    elements.newer.innerHTML = newer ? `${shortDate(newer)} <span aria-hidden="true">→</span>` : "Next <span aria-hidden=\"true\">→</span>";
    elements.older.dataset.date = older || "";
    elements.newer.dataset.date = newer || "";
    elements.today.disabled = index === 0;
    elements.nav.hidden = archiveDates.length < 2;
  }

  function wireEvents() {
    elements.smaller.addEventListener("click", () => applyTypeSize(typeIndex - 1, true));
    elements.reset.addEventListener("click", () => applyTypeSize(defaultTypeIndex, true));
    elements.larger.addEventListener("click", () => applyTypeSize(typeIndex + 1, true));
    elements.older.addEventListener("click", () => loadEdition(elements.older.dataset.date));
    elements.newer.addEventListener("click", () => loadEdition(elements.newer.dataset.date));
    elements.today.addEventListener("click", () => loadEdition(null));
  }

  async function start() {
    applyTypeSize(typeIndex);
    wireEvents();
    await loadArchive();
    const requestedDate = new URLSearchParams(window.location.search).get("date");
    const safeDate = /^\d{4}-\d{2}-\d{2}$/.test(requestedDate || "") ? requestedDate : null;
    await loadEdition(safeDate);
    if ("serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    }
  }

  start();
})();

