(function(){
  const PLAN_RAW = __PLAN_JSON__;
  const WRAP_ARROWS = __WRAP_ARROWS__;
  let PLAN = [];
  if (Array.isArray(PLAN_RAW)) {
    PLAN = PLAN_RAW.map(function(row){
      if (!row || typeof row !== 'object') {
        return null;
      }
      const didVal = Object.prototype.hasOwnProperty.call(row, 'did') ? row.did :
                     (Object.prototype.hasOwnProperty.call(row, 'id') ? row.id : null);
      const isoVal = typeof row.iso === 'string' ? row.iso : '';
      if (didVal === null || isoVal === '') {
        return null;
      }
      const orderVal = Number(row.order);
      const orderNum = Number.isFinite(orderVal) ? orderVal : 0;
      return { did: String(didVal), iso: isoVal, order: orderNum };
    }).filter(Boolean);
  }
  window.WP_PLAN = PLAN;
  const DECKS = window.WP_DECKS = __DECKS_JSON__;
  const TODAY_ISO = __TODAY_ISO__;
  const ensureStyle = () => {
    let st = document.getElementById('wp-style');
    if (!st) {
      st = document.createElement('style');
      st.id = 'wp-style';

      const css = getComputedStyle(document.body);
      const root = getComputedStyle(document.documentElement);
      const pick = (name, fallback) => {
        const bodyVal = css.getPropertyValue(name).trim();
        if (bodyVal) return bodyVal;
        const rootVal = root.getPropertyValue(name).trim();
        if (rootVal) return rootVal;
        return fallback;
      };

      const frameBorder = pick('--frame-border', '#dcdcdc');
      const panelBg = pick('--panel-bg', '#ffffff');
      const textColor = pick('--text-fg', '#1f1f1f');
      const muted = pick('--text-muted', '#6c6c6c');
      const buttonBg = pick('--button-bg', '#f6f6f6');
      const buttonHover = pick('--button-bg-hover', '#ebebeb');
      const accent = pick('--focus-border', '#4c9aff');

      st.textContent = `
        #wp-wrap{margin:16px 0;padding:16px;border:1px solid ${frameBorder};border-radius:12px;background:${panelBg};color:${textColor};font-size:13px;}
        #wp-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap;}
        .wp-title{font-weight:600;font-size:15px;}
        .wp-range{min-width:160px;text-align:center;font-weight:500;}
        .wp-btn{padding:4px 10px;border:1px solid ${frameBorder};border-radius:8px;background:${buttonBg};cursor:pointer;font-size:12px;transition:background .12s;}
        .wp-btn:hover{background:${buttonHover};}
        #planner-grid{display:grid;grid-template-columns:repeat(5,minmax(220px,1fr));gap:24px;align-items:start;margin-top:8px;}
        .cell{background:${panelBg};border:1px solid transparent;border-radius:0;display:flex;flex-direction:column;min-height:160px;}
        .cell.today .cell-date{color:${accent};}
        .cell.today .cell-header{border-bottom-color:${accent};}
        .cell-header{display:flex;justify-content:space-between;align-items:flex-end;padding:8px 0;border-bottom:2px solid #0f0f0f;font-weight:600;}
        .wp-day-controls{display:flex;gap:4px;align-items:center;}
        .wp-day-controls .wp-btn{padding:2px 6px;border-radius:6px;}
        .cell-date{font-size:18px;font-weight:700;color:#111;}
        .cell-weekday{font-size:14px;font-weight:500;color:${muted};}
        .cell-list{display:flex;flex-direction:column;padding:0;margin-top:10px;gap:8px;flex:1;}
        .cell-item{padding:10px 14px;border:1px solid rgba(17,17,17,0.08);border-radius:12px;background:linear-gradient(180deg,#ffffff,#f8f8f8);box-shadow:0 1px 2px rgba(17,17,17,0.08);cursor:pointer;user-select:none;font-size:15px;color:#111;position:relative;transition:background .12s, box-shadow .12s;}
        .cell-item::before{content:'';position:absolute;left:14px;top:50%;transform:translateY(-50%);width:4px;height:50%;border-radius:2px;background:rgba(17,17,17,0.18);}
        .cell-item:hover{background:linear-gradient(180deg,#f9f9f9,#f0f0f0);box-shadow:0 2px 6px rgba(17,17,17,0.14);}
      `
      document.head.appendChild(st);
    }
  };

  ensureStyle();

  window.WP_send = function (msg) {
    try {
      if (window.pycmd) { pycmd(msg); return; }
      if (window.anki && typeof window.anki.bridgeCommand === "function") {
        window.anki.bridgeCommand(msg); return;
      }
      if (window.ankiBridgeCommand) { ankiBridgeCommand(msg); return; }
      throw new Error("No Anki bridge function found");
    } catch (e) {
      console.error("Week Planner bridge error:", e, "msg=", msg);
    }
  };

  const root = document.querySelector('#deckbrowser') || document.body;
  const container = root.querySelector(':scope > .overview') || root;
  const existing = container.querySelector('#wp-wrap');
  if (existing) existing.remove();

  const wrap = document.createElement('div');
  wrap.id = 'wp-wrap';
  wrap.innerHTML = `
    <div id="wp-head">
      <div class="wp-title">Week Planner</div>
      <span id="wp-range" class="wp-range"></span>
    </div>
    <div id="planner-grid"></div>
  `;
  container.insertAdjacentElement('afterbegin', wrap);

  const plannerGrid = wrap.querySelector('#planner-grid');
  const rangeLabel = wrap.querySelector('#wp-range');

  const deckIndex = new Map();
  const deckByName = new Map();
  for (const deck of DECKS) {
    if (deck && deck.id != null) {
      const idStr = String(deck.id);
      deckIndex.set(idStr, deck);
      if (deck.name) {
        const nameKey = String(deck.name).trim().toLowerCase();
        if (nameKey) {
          deckByName.set(nameKey, deck);
        }
      }
    }
  }
  const deckOptions = Array.from(deckIndex.values()).sort(function(a, b) {
    const nameA = (a && a.name ? String(a.name) : '').toLowerCase();
    const nameB = (b && b.name ? String(b.name) : '').toLowerCase();
    if (nameA < nameB) return -1;
    if (nameA > nameB) return 1;
    return 0;
  });

  const STATE = {
    anchorIso: TODAY_ISO
  };

  const formatterWeekday = new Intl.DateTimeFormat(undefined, { weekday: 'short' });
  const formatterDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' });
  function parseISO(iso) {
    const parts = (iso || '').split('-').map(Number);
    const dt = new Date();
    if (parts.length === 3) {
      dt.setFullYear(parts[0]);
      dt.setMonth(parts[1] - 1);
      dt.setDate(parts[2]);
    }
    dt.setHours(0, 0, 0, 0);
    return dt;
  }

  function isoFromDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + d;
  }

  function addDays(date, n) {
    const dt = new Date(date.getTime());
    dt.setDate(dt.getDate() + n);
    return dt;
  }

  function formatRange(anchorIso) {
    const start = parseISO(anchorIso || TODAY_ISO);
    const end = addDays(start, 4);
    const startText = formatterDate.format(start);
    const endText = formatterDate.format(end);
    const startYear = start.getFullYear();
    const endYear = end.getFullYear();
    if (startYear !== endYear) {
      return startText + ' ' + startYear + ' – ' + endText + ' ' + endYear;
    }
    return startText + ' – ' + endText + ' ' + startYear;
  }

  function labelParts(iso) {
    const dt = parseISO(iso);
    return {
      weekday: formatterWeekday.format(dt),
      date: formatterDate.format(dt)
    };
  }

  function deckById(did) {
    return deckIndex.get(String(did)) || null;
  }

  function groupFromList(list) {
    const groups = new Map();
    if (!Array.isArray(list)) {
      return groups;
    }
    for (const entry of list) {
      if (!entry || typeof entry !== 'object') {
        continue;
      }
      const iso = typeof entry.iso === 'string' ? entry.iso : '';
      const did = entry.did != null ? String(entry.did) : '';
      if (!iso || !did) {
        continue;
      }
      const orderVal = Number(entry.order);
      const orderNum = Number.isFinite(orderVal) ? orderVal : 0;
      if (!groups.has(iso)) {
        groups.set(iso, []);
      }
      groups.get(iso).push({ did: did, order: orderNum });
    }
    return groups;
  }

  function rebuildPlan(groups) {
    const result = [];
    const isoKeys = Array.from(groups.keys()).sort();
    for (const iso of isoKeys) {
      const bucket = (groups.get(iso) || []).slice().sort(function(a, b) {
        if (a.order !== b.order) {
          return a.order - b.order;
        }
        if (a.did < b.did) return -1;
        if (a.did > b.did) return 1;
        return 0;
      });
      const seen = new Set();
      bucket.forEach(function(entry, idx) {
        const key = iso + '::' + entry.did;
        if (seen.has(key)) {
          return;
        }
        seen.add(key);
        result.push({ did: entry.did, iso: iso, order: idx });
      });
    }
    return result;
  }

  function currentWeekDates() {
    const start = parseISO(STATE.anchorIso || TODAY_ISO);
    const dates = [];
    for (let i = 0; i < 5; i++) {
      dates.push(isoFromDate(addDays(start, i)));
    }
    return dates;
  }

  function decksForIso(iso) {
    return PLAN.filter(function(entry) {
      return entry && entry.iso === iso;
    }).sort(function(a, b) {
      if (a.order !== b.order) {
        return a.order - b.order;
      }
      if (String(a.did) < String(b.did)) return -1;
      if (String(a.did) > String(b.did)) return 1;
      return 0;
    }).map(function(entry) {
      return { did: String(entry.did), deck: deckById(entry.did) };
    });
  }

  const cells = new Map();

  function applyPlan(groups) {
    PLAN = rebuildPlan(groups);
    window.WP_PLAN = PLAN;
    renderAssignments();
  }

  function normalizeBucket(entries) {
    return entries.map(function(entry, idx) {
      return { did: entry.did, order: idx };
    });
  }

  function setBucket(groups, iso, entries) {
    const bucket = Array.isArray(entries) ? entries : [];
    if (bucket.length) {
      groups.set(iso, normalizeBucket(bucket));
    } else {
      groups.delete(iso);
    }
  }

  function assignDeckToIso(did, iso) {
    if (!iso) return;
    const didKey = String(did);
    const groups = groupFromList(PLAN);
    const current = groups.has(iso) ? groups.get(iso).slice() : [];
    const filtered = current.filter(function(entry) {
      return entry.did !== didKey;
    });
    filtered.push({ did: didKey, order: filtered.length });
    setBucket(groups, iso, filtered);
    applyPlan(groups);
    WP_send(`wp_assign:${didKey}:${iso}`);
  }

  function removeDeckFromIso(did, iso) {
    const didKey = String(did);
    if (!iso) return false;
    const groups = groupFromList(PLAN);
    if (!groups.has(iso)) return false;
    const filtered = groups.get(iso).filter(function(entry) {
      return entry.did !== didKey;
    });
    setBucket(groups, iso, filtered);
    applyPlan(groups);
    WP_send(`wp_remove:${didKey}:${iso}`);
    return true;
  }

  function removeHighestOrder(iso) {
    if (!iso) return;
    const groups = groupFromList(PLAN);
    if (!groups.has(iso)) {
      return;
    }
    const bucket = groups.get(iso).slice().sort(function(a, b) {
      if (a.order !== b.order) {
        return a.order - b.order;
      }
      if (a.did < b.did) return -1;
      if (a.did > b.did) return 1;
      return 0;
    });
    if (!bucket.length) {
      return;
    }
    const last = bucket[bucket.length - 1];
    removeDeckFromIso(last.did, iso);
  }

  function targetIsoForDelta(iso, delta) {
    if (!iso || !Number.isFinite(delta) || delta === 0) {
      return null;
    }
    const date = parseISO(iso);
    const weekday = date.getDay();
    if (delta < 0) {
      if (weekday === 1 && !WRAP_ARROWS) {
        return null;
      }
      if (weekday === 1 && WRAP_ARROWS) {
        return isoFromDate(addDays(date, -1));
      }
      return isoFromDate(addDays(date, delta));
    }
    if (delta > 0) {
      if (weekday === 0 && !WRAP_ARROWS) {
        return null;
      }
      if (weekday === 0 && WRAP_ARROWS) {
        return TODAY_ISO;
      }
      return isoFromDate(addDays(date, delta));
    }
    return iso;
  }

  function shiftHighestDeck(iso, delta) {
    const targetIso = targetIsoForDelta(iso, delta);
    if (!targetIso || targetIso === iso) {
      return;
    }
    const groups = groupFromList(PLAN);
    if (!groups.has(iso)) {
      return;
    }
    const bucket = groups.get(iso).slice().sort(function(a, b) {
      if (a.order !== b.order) {
        return a.order - b.order;
      }
      if (a.did < b.did) return -1;
      if (a.did > b.did) return 1;
      return 0;
    });
    if (!bucket.length) {
      return;
    }
    const moved = bucket.pop();
    const didKey = String(moved.did);
    setBucket(groups, iso, bucket);
    const targetBucket = groups.has(targetIso) ? groups.get(targetIso).slice() : [];
    targetBucket.push({ did: didKey, order: targetBucket.length });
    setBucket(groups, targetIso, targetBucket);
    applyPlan(groups);
    const orderIndex = targetBucket.length - 1;
    WP_send(`wp_move:${didKey}:${iso}:${targetIso}:${orderIndex}`);
  }

  function buildGrid() {
    plannerGrid.innerHTML = '';
    cells.clear();
    const dates = currentWeekDates();
    dates.forEach(function(iso) {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.dataset.iso = iso;
      if (iso === TODAY_ISO) {
        cell.classList.add('today');
      }
      const header = document.createElement('div');
      header.className = 'cell-header';
      const parts = labelParts(iso);
      header.innerHTML = `
        <span class="cell-date">${parts.date}</span>
        <span class="cell-weekday">${parts.weekday}</span>
      `;
      // Add buttons to manage decks for this day.
      const controls = document.createElement('div');
      controls.className = 'wp-day-controls';

      const prevBtn = document.createElement('button');
      prevBtn.className = 'wp-btn wp-prev-btn';
      prevBtn.title = 'Move latest deck to previous day';
      prevBtn.textContent = '<';
      prevBtn.addEventListener('click', function(evt) {
        evt.stopPropagation();
        shiftHighestDeck(iso, -1);
      });

      const addBtn = document.createElement('button');
      addBtn.className = 'wp-btn wp-add-btn';
      addBtn.title = 'Add deck';
      addBtn.textContent = '+';
      addBtn.addEventListener('click', function(evt) {
        evt.stopPropagation();
        const existing = document.querySelector('.deck-select-popup');
        if (existing) existing.remove();

        const popup = document.createElement('div');
        popup.className = 'deck-select-popup';
        popup.style.position = 'absolute';
        popup.style.background = '#fff';
        popup.style.border = '1px solid #ccc';
        popup.style.borderRadius = '6px';
        popup.style.padding = '6px';
        popup.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
        popup.style.maxHeight = '220px';
        popup.style.overflowY = 'auto';
        popup.style.minWidth = '200px';
        popup.style.zIndex = '9999';
        popup.style.fontSize = '13px';

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Search deck...';
        input.style.width = '100%';
        input.style.marginBottom = '6px';
        input.style.padding = '4px 6px';
        input.style.boxSizing = 'border-box';
        popup.appendChild(input);

        const list = document.createElement('div');
        popup.appendChild(list);

        function renderList(filterText) {
          list.innerHTML = '';
          const query = (filterText || '').trim().toLowerCase();
          const matches = deckOptions.filter(function(deck) {
            const name = deck && deck.name ? String(deck.name) : '';
            return !query || name.toLowerCase().includes(query);
          }).slice(0, 50);
          if (!matches.length) {
            const empty = document.createElement('div');
            empty.textContent = 'No decks found';
            empty.style.padding = '6px';
            empty.style.color = '#666';
            list.appendChild(empty);
            return;
          }
          matches.forEach(function(deck) {
            const item = document.createElement('div');
            item.textContent = deck.name || ('Deck ' + deck.id);
            item.style.padding = '4px 6px';
            item.style.cursor = 'pointer';
            item.addEventListener('mouseover', function() {
              item.style.background = '#f0f0f0';
            });
            item.addEventListener('mouseout', function() {
              item.style.background = '';
            });
            item.addEventListener('click', function() {
              popup.remove();
              const did = String(deck.id);
              assignDeckToIso(did, iso);
            });
            list.appendChild(item);
          });
        }

        input.addEventListener('input', function() {
          renderList(input.value);
        });

        renderList('');

        document.body.appendChild(popup);
        const rect = addBtn.getBoundingClientRect();
        popup.style.left = rect.left + 'px';
        popup.style.top = rect.bottom + window.scrollY + 'px';

        const closePopup = function(e) {
          if (!popup.contains(e.target)) {
            popup.remove();
            document.removeEventListener('click', closePopup);
          }
        };
        setTimeout(function() {
          document.addEventListener('click', closePopup);
        }, 0);

        input.focus();
      });

      const removeBtn = document.createElement('button');
      removeBtn.className = 'wp-btn wp-remove-btn';
      removeBtn.title = 'Remove latest deck';
      removeBtn.textContent = '−';
      removeBtn.addEventListener('click', function(evt) {
        evt.stopPropagation();
        removeHighestOrder(iso);
      });

      const nextBtn = document.createElement('button');
      nextBtn.className = 'wp-btn wp-next-btn';
      nextBtn.title = 'Move latest deck to next day';
      nextBtn.textContent = '>';
      nextBtn.addEventListener('click', function(evt) {
        evt.stopPropagation();
        shiftHighestDeck(iso, 1);
      });

      controls.appendChild(prevBtn);
      controls.appendChild(addBtn);
      controls.appendChild(removeBtn);
      controls.appendChild(nextBtn);

      const prevTarget = targetIsoForDelta(iso, -1);
      if (!prevTarget || prevTarget === iso) {
        prevBtn.style.display = 'none';
      }
      const nextTarget = targetIsoForDelta(iso, 1);
      if (!nextTarget || nextTarget === iso) {
        nextBtn.style.display = 'none';
      }

      header.appendChild(controls);
      const list = document.createElement('div');
      list.className = 'cell-list';

      cell.appendChild(header);
      cell.appendChild(list);
      plannerGrid.appendChild(cell);

      cells.set(iso, {
        cell: cell,
        list: list
      });
    });
  }

  function makeDeckCard(deck, did, iso, order) {
    const card = document.createElement('div');
    card.className = 'cell-item';
    card.dataset.did = did;
    card.dataset.iso = iso;
    card.dataset.order = String(order);
    card.textContent = deck && deck.name ? deck.name : ('Deck ' + did);
    card.addEventListener('click', handleDeckClick);
    return card;
  }

  function handleDeckClick(e) {
    const target = e.currentTarget;
    const did = target.dataset.did;
    const iso = target.dataset.iso;
    if (!did) return;
    if (e.altKey) {
      e.preventDefault();
      e.stopPropagation();
      removeDeckFromIso(did, iso);
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    WP_send('wp_open:' + did);
  }

  function renderAssignments() {
    cells.forEach(function(info, iso) {
      info.list.innerHTML = '';
      const rows = decksForIso(iso);
      rows.forEach(function(row, idx) {
        const card = makeDeckCard(row.deck, row.did, iso, idx);
        info.list.appendChild(card);
      });
      info.cell.classList.toggle('today', iso === TODAY_ISO);
    });
    updateRangeLabel();
  }

  function updateRangeLabel() {
    rangeLabel.textContent = formatRange(STATE.anchorIso);
  }

  function renderWeekView() {
    buildGrid();
    renderAssignments();
  }

  window.WP_setPlan = function(nextPlan) {
    try {
      const normalized = Array.isArray(nextPlan) ? nextPlan.map(function(entry) {
        if (!entry || typeof entry !== 'object') {
          return null;
        }
        const iso = typeof entry.iso === 'string' ? entry.iso : '';
        const didAny = entry.did != null ? entry.did : entry.id;
        const did = didAny != null ? String(didAny) : '';
        if (!iso || !did) {
          return null;
        }
        const orderVal = Number(entry.order);
        const order = Number.isFinite(orderVal) ? orderVal : 0;
        return { iso: iso, did: did, order: order };
      }).filter(Boolean) : [];
      applyPlan(groupFromList(normalized));
    } catch (err) {
      console.error('Week Planner setPlan failed', err);
    }
  };

  STATE.anchorIso = TODAY_ISO;
  PLAN = rebuildPlan(groupFromList(PLAN));
  window.WP_PLAN = PLAN;
  renderWeekView();
})();
