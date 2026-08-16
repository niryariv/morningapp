(() => {
  "use strict";

  const MIX_SIZE = 7;

  function shuffled(items, random) {
    const copy = [...items];
    for (let index = copy.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(random() * (index + 1));
      [copy[index], copy[swap]] = [copy[swap], copy[index]];
    }
    return copy;
  }

  function validItem(item) {
    return item && typeof item === "object"
      && typeof item.id === "string" && item.id.trim()
      && typeof item.category === "string" && item.category.trim()
      && typeof item.title === "string" && item.title.trim();
  }

  function itemKeys(item) {
    const keys = [`id:${item.id}`];
    if (typeof item.url === "string" && item.url.trim()) keys.push(`url:${item.url.trim()}`);
    return keys;
  }

  function chooseMix(pool, currentItems, random = Math.random) {
    if (!Array.isArray(pool) || !Array.isArray(currentItems) || typeof random !== "function") return null;

    const currentKeys = new Set(currentItems.filter(validItem).flatMap(itemKeys));
    const ids = new Set();
    const available = pool.filter((item) => {
      if (!validItem(item) || ids.has(item.id) || itemKeys(item).some((key) => currentKeys.has(key))) return false;
      ids.add(item.id);
      return true;
    });
    const classics = shuffled(available.filter((item) => item.category === "classics"), random);
    const poems = shuffled(available.filter((item) => item.category === "poetry"), random);
    const general = shuffled(
      available.filter((item) => item.category !== "classics" && item.category !== "poetry"),
      random,
    );
    if (!classics.length || !poems.length || general.length < MIX_SIZE - 2) return null;

    const selected = [classics[0], poems[0]];
    const categories = new Map([["classics", 1], ["poetry", 1]]);
    const sources = new Map();
    for (const item of selected) {
      if (item.source) sources.set(item.source, (sources.get(item.source) || 0) + 1);
    }

    while (selected.length < MIX_SIZE) {
      let bestIndex = 0;
      let bestPenalty = Number.POSITIVE_INFINITY;
      general.forEach((item, index) => {
        const penalty = (categories.get(item.category) || 0) * 4
          + (sources.get(item.source) || 0) * 2;
        if (penalty < bestPenalty) {
          bestPenalty = penalty;
          bestIndex = index;
        }
      });
      const [item] = general.splice(bestIndex, 1);
      selected.push(item);
      categories.set(item.category, (categories.get(item.category) || 0) + 1);
      if (item.source) sources.set(item.source, (sources.get(item.source) || 0) + 1);
    }

    const mixed = shuffled(selected, random);
    const astronomyIndex = mixed.findIndex((item) => item.category === "astronomy");
    if (astronomyIndex > 0) mixed.unshift(mixed.splice(astronomyIndex, 1)[0]);
    return mixed;
  }

  window.MorningShuffle = Object.freeze({ chooseMix });
})();
