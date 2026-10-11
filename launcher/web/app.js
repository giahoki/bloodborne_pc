// The launcher page: draws the pages described by bbport_launcher_web.py (Api.init) and talks
// to it through window.pywebview.api. Opened in a plain browser (no pywebview) it uses a small
// stand-in so the look can be checked without the game.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  };
  let api, data, values = {}, current = 'play', lastState = null, logLines = 0;
  const MAX_LOG = 6000;
  const binders = {}; // 'store:key' -> functions that show a new value

  function toast(text, kind) {
    if (!text) return;
    const t = el('div', 'toast' + (kind === 'error' ? ' error' : ''), text);
    $('toasts').appendChild(t);
    setTimeout(() => { t.style.transition = 'opacity .5s'; t.style.opacity = '0'; }, kind === 'error' ? 7000 : 4500);
    setTimeout(() => t.remove(), kind === 'error' ? 7600 : 5100);
  }
  function result(r) {
    if (!r) return;
    if (r.error) toast(r.error, 'error');
    if (r.info) toast(r.info);
    if (r.page) show(r.page);
    if (r.values) Object.entries(r.values).forEach(([id, v]) => showValue(id, v));
    if (r.state) applyState(r.state);
  }

  // ---- key bindings ---------------------------------------------------------------------------
  // Bindings are SDL key names ("Space", "Return", "Left Shift"), Mouse1..5 or WheelUp/Down, with
  // optional Shift+/Ctrl+/Alt+ (src/runtime_pad.c reads them).
  const CODE_TO_SDL = {
    Space: 'Space', Enter: 'Return', NumpadEnter: 'Keypad Enter', Escape: 'Escape', Backspace: 'Backspace',
    Tab: 'Tab', ShiftLeft: 'Left Shift', ShiftRight: 'Right Shift', ControlLeft: 'Left Ctrl',
    ControlRight: 'Right Ctrl', AltLeft: 'Left Alt', AltRight: 'Right Alt', ArrowUp: 'Up', ArrowDown: 'Down',
    ArrowLeft: 'Left', ArrowRight: 'Right', CapsLock: 'CapsLock', Backquote: '`', Minus: '-', Equal: '=',
    BracketLeft: '[', BracketRight: ']', Backslash: '\\', Semicolon: ';', Quote: "'", Comma: ',', Period: '.',
    Slash: '/', Insert: 'Insert', Delete: 'Delete', Home: 'Home', End: 'End', PageUp: 'PageUp',
    PageDown: 'PageDown', NumpadAdd: 'Keypad +', NumpadSubtract: 'Keypad -', NumpadMultiply: 'Keypad *',
    NumpadDivide: 'Keypad /', NumpadDecimal: 'Keypad .',
  };
  const RESERVED = ['Insert', 'F9', 'F10', 'Left Alt'];
  function sdlName(code) {
    if (CODE_TO_SDL[code]) return CODE_TO_SDL[code];
    let m;
    if ((m = /^Key([A-Z])$/.exec(code))) return m[1];
    if ((m = /^Digit(\d)$/.exec(code))) return m[1];
    if ((m = /^Numpad(\d)$/.exec(code))) return `Keypad ${m[1]}`;
    if ((m = /^F(\d{1,2})$/.exec(code))) return `F${m[1]}`;
    return null;
  }
  function prettyKey(binding) {
    const ru = data && data.lang === 'ru';
    const names = ru
      ? { Mouse1: 'ЛКМ', Mouse2: 'ПКМ', Mouse3: 'Колесо', Mouse4: 'Мышь 4', Mouse5: 'Мышь 5', WheelUp: 'Колесо ↑',
          WheelDown: 'Колесо ↓', Space: 'Пробел', Return: 'Enter', Escape: 'Esc', Up: '↑', Down: '↓', Left: '←', Right: '→',
          'Left Shift': 'Shift', 'Right Shift': 'Правый Shift', 'Left Ctrl': 'Ctrl', 'Right Ctrl': 'Правый Ctrl', 'Right Alt': 'Правый Alt' }
      : { Mouse1: 'LMB', Mouse2: 'RMB', Mouse3: 'MMB', Mouse4: 'Mouse 4', Mouse5: 'Mouse 5', WheelUp: 'Wheel ↑',
          WheelDown: 'Wheel ↓', Return: 'Enter', Escape: 'Esc', Up: '↑', Down: '↓', Left: '←', Right: '→',
          'Left Shift': 'Shift', 'Left Ctrl': 'Ctrl' };
    return binding.split('+').map((part) => names[part] || part).join(' + ');
  }
  let capturing = null; // {slot, finish}
  function stopCapture() {
    if (!capturing) return;
    capturing.slot.classList.remove('capturing');
    capturing.cancel();
    capturing = null;
  }
  function bindings(item) {
    const wrap = el('div', 'bindings full');
    for (const group of item.groups) {
      wrap.append(el('div', 'bind-group', group.title));
      for (const action of group.actions) {
        const id = `ini:${action.key}`;
        const row = el('div', 'bind-row');
        row.append(el('div', 'bind-label', action.label));
        const slots = [0, 1].map(() => el('button', 'bind-slot'));
        let list = [];
        const paint = (v) => {
          list = String(v ?? '').split('|').filter(Boolean);
          slots.forEach((s, i) => {
            s.textContent = list[i] ? prettyKey(list[i]) : '—';
            s.classList.toggle('empty', !list[i]);
            s.title = list[i] || '';
          });
          row.classList.toggle('changed', String(v ?? '') !== action.default);
        };
        bind(id, paint);
        const save = (next) => setValue(action.key, 'ini', next.filter(Boolean).join('|'));
        slots.forEach((slot, i) => {
          slot.addEventListener('click', (e) => {
            e.stopPropagation();
            stopCapture();
            slot.classList.add('capturing');
            slot.textContent = data.lang === 'ru' ? 'Нажмите…' : 'Press…';
            const take = (name) => {
              if (RESERVED.includes(name.replace(/^(Shift|Ctrl|Alt)\+/g, ''))) {
                toast((data.lang === 'ru' ? 'Эта клавиша занята портом: ' : 'Reserved by the port: ') + prettyKey(name), 'error');
                return;
              }
              const next = list.slice();
              next[i] = name;
              capturing.slot.classList.remove('capturing');
              cleanup();
              capturing = null;
              save(next);
            };
            const mods = (e) => {
              if (e.shiftKey) return 'Shift+';
              if (e.ctrlKey) return 'Ctrl+';
              if (e.altKey) return 'Alt+';
              return '';
            };
            const onKey = (e) => {
              e.preventDefault();
              e.stopPropagation();
              const name = sdlName(e.code);
              if (!name) return;
              const isMod = /Shift|Ctrl|Alt/.test(name);
              take(isMod ? name : mods(e) + name);
            };
            const onMouse = (e) => {
              if (e.button === 0 && e.target !== slot) { stopCapture(); return; } // a click elsewhere cancels
              if (e.target === slot && e.button === 0 && !slot.dataset.armed) return;
              e.preventDefault();
              e.stopPropagation();
              take(mods(e) + ['Mouse1', 'Mouse3', 'Mouse2', 'Mouse4', 'Mouse5'][e.button]);
            };
            const onWheel = (e) => { e.preventDefault(); take(mods(e) + (e.deltaY < 0 ? 'WheelUp' : 'WheelDown')); };
            const onContext = (e) => e.preventDefault();
            const cleanup = () => {
              window.removeEventListener('keydown', onKey, true);
              window.removeEventListener('mousedown', onMouse, true);
              window.removeEventListener('wheel', onWheel, { capture: true });
              window.removeEventListener('contextmenu', onContext, true);
              delete slot.dataset.armed;
            };
            // the click that started the capture must not be taken as Mouse1
            setTimeout(() => { slot.dataset.armed = '1'; }, 0);
            window.addEventListener('keydown', onKey, true);
            window.addEventListener('mousedown', onMouse, true);
            window.addEventListener('wheel', onWheel, { capture: true, passive: false });
            window.addEventListener('contextmenu', onContext, true);
            capturing = { slot, cancel: () => { cleanup(); paint(values[id]); } };
          });
          slot.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            stopCapture();
            const next = list.slice();
            next[i] = '';
            save(next);
          });
        });
        const clear = el('button', 'bind-clear', '✕');
        clear.title = data.lang === 'ru' ? 'Очистить' : 'Clear';
        clear.addEventListener('click', () => { stopCapture(); save([]); });
        row.append(...slots, clear);
        wrap.append(row);
      }
    }
    return wrap;
  }

  // ---- values ---------------------------------------------------------------------------------
  function bind(id, fn) { (binders[id] = binders[id] || []).push(fn); }
  function showValue(id, value) {
    values[id] = value;
    (binders[id] || []).forEach((fn) => fn(value));
  }
  async function setValue(key, store, value) {
    const id = `${store}:${key}`;
    showValue(id, value);
    const r = await api.set(key, store, value);
    if (r && r.reload) { sessionStorage.setItem('bb-page', current); location.reload(); return; }
    if (r && r.changed) Object.entries(r.changed).forEach(([k, v]) => showValue(k, v));
    if (r && r.state) applyState(r.state);
  }

  // ---- widgets --------------------------------------------------------------------------------
  function choice(item) {
    const id = `${item.store}:${item.key}`;
    const s = el('select');
    item.options.forEach(([v, label]) => { const o = el('option', null, label); o.value = v; s.appendChild(o); });
    bind(id, (v) => { s.value = String(v); if (s.selectedIndex < 0) s.selectedIndex = 0; });
    s.addEventListener('change', () => setValue(item.key, item.store, s.value));
    return s;
  }
  function check(item) {
    const id = `${item.store}:${item.key}`;
    const label = el('label', 'check');
    const input = el('input');
    input.type = 'checkbox';
    label.append(input, el('span', 'box'), el('span', null, item.label));
    bind(id, (v) => { input.checked = !!v; });
    input.addEventListener('change', () => setValue(item.key, item.store, input.checked));
    return label;
  }
  function slider(item) {
    const id = `${item.store}:${item.key}`;
    const wrap = el('div', 'slider');
    const input = el('input');
    input.type = 'range';
    input.min = item.min; input.max = item.max; input.step = item.step;
    const out = el('output');
    const paint = (v) => {
      input.value = v;
      out.textContent = Number(v).toFixed(2);
      input.style.setProperty('--fill', `${(v - item.min) / (item.max - item.min) * 100}%`);
    };
    bind(id, paint);
    input.addEventListener('input', () => paint(input.value));
    input.addEventListener('change', () => setValue(item.key, item.store, parseFloat(input.value)));
    wrap.append(input, out);
    return wrap;
  }
  function entry(item) {
    const id = `${item.store}:${item.key}`;
    const input = el('input');
    input.type = item.secret ? 'password' : 'text';
    input.spellcheck = false;
    bind(id, (v) => { if (document.activeElement !== input) input.value = v ?? ''; });
    let timer;
    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => setValue(item.key, item.store, input.value), 400); });
    return input;
  }
  function folder(item) {
    const wrap = el('div', 'folder');
    const input = entry(item);
    const browse = el('button', 'btn small', data.text.browse);
    browse.addEventListener('click', async () => {
      const r = await api.browse(item.key);
      if (r) {
        showValue(`app:${item.key}`, r.value);
        if (item.key === 'game_dir') setArt(r.art);
        if (item.key === 'mods_dir' || item.key === 'patches_dir') refreshLists();
        applyState(r.state);
      }
    });
    const open = el('button', 'btn small ghost', data.text.open);
    open.addEventListener('click', () => api.open_path(item.key));
    wrap.append(input, browse, open);
    return wrap;
  }

  function addRow(form, label, widget, hint) {
    form.append(el('div', 'label', label), widget);
    if (hint) form.append(el('div', 'hint', hint));
  }

  function renderItems(form, items) {
    for (const item of items) {
      switch (item.t) {
        case 'section': form.append(el('div', 'section full', item.label)); break;
        case 'note': form.append(el('div', 'note full', item.text)); break;
        case 'warn': {
          const w = el('div', 'warnbox full');
          w.hidden = true;
          w.dataset.warn = '1';
          form.append(w);
          break;
        }
        case 'choice': addRow(form, item.label, choice(item), item.hint); break;
        case 'slider': addRow(form, item.label, slider(item), item.hint); break;
        case 'entry': addRow(form, item.label, entry(item), item.hint); break;
        case 'folder': addRow(form, item.label, folder(item), item.hint); break;
        case 'check': {
          const c = check(item);
          c.classList.add('full');
          form.append(c);
          if (item.hint) form.append(el('div', 'hint full', item.hint));
          break;
        }
        case 'buttons': {
          const b = el('div', 'buttons full');
          for (const [label, action] of item.items) {
            const btn = el('button', 'btn', label);
            btn.addEventListener('click', async () => result(await api.action(action)));
            b.append(btn);
          }
          form.append(b);
          break;
        }
        case 'keys': {
          const k = el('div', 'keys full');
          item.rows.forEach(([key, value]) => {
            const kc = el('div', 'k');
            key.split(' / ').forEach((part, j) => { if (j) kc.append(' / '); kc.append(el('span', null, part)); });
            k.append(kc, el('div', 'v', value));
          });
          form.append(k);
          break;
        }
        case 'fsr4': {
          const box = el('div', 'full');
          const text = el('div', 'note');
          const btn = el('button', 'btn', item.label);
          const bar = el('div', 'progress');
          const fill = el('div');
          bar.append(fill);
          btn.style.marginTop = '10px';
          btn.addEventListener('click', async () => { btn.disabled = true; result(await api.download_fsr4()); });
          box.append(text, btn, bar);
          box.dataset.fsr4 = '1';
          box.update = (f) => {
            text.textContent = f.text;
            fill.style.width = `${f.done / f.total * 100}%`;
            btn.disabled = f.busy || f.done === f.total;
          };
          form.append(box);
          break;
        }
        case 'online_test': {
          const wrap = el('div', 'full');
          const btn = el('button', 'btn', item.label);
          const out = el('div', 'result');
          out.style.marginTop = '10px';
          btn.addEventListener('click', async () => {
            out.textContent = data.text.checking;
            out.textContent = await api.test_connection();
          });
          wrap.append(btn, out);
          form.append(wrap);
          break;
        }
        case 'bindings': form.append(bindings(item)); break;
        case 'mods': form.append(Object.assign(el('div', 'list full'), { id: 'mods-list' })); break;
        case 'patches': form.append(Object.assign(el('div', 'list full'), { id: 'patches-list' })); break;
      }
    }
  }

  function renderPage(page) {
    const sec = el('section', 'page');
    sec.id = `page-${page.id}`;
    const head = el('div', 'page-head');
    const titles = el('div');
    titles.append(el('h1', null, page.title), el('div', 'lead', page.subtitle));
    head.append(titles);
    const panel = el('div', 'panel');
    const form = el('div', 'form');
    renderItems(form, page.items);
    panel.append(form);
    sec.append(head, panel);
    return sec;
  }

  async function refreshLists() {
    const mods = $('mods-list'), patches = $('patches-list');
    if (!mods) return;
    const r = await api.lists();
    mods.replaceChildren();
    if (!r.mods.length) mods.append(el('div', 'note', r.no_mods));
    r.mods.forEach((m, i) => {
      const row = el('div', 'row');
      const arrows = el('div', 'arrows');
      const up = el('button', 'btn small ghost', '▲'), down = el('button', 'btn small ghost', '▼');
      up.addEventListener('click', async () => { await api.move_mod(i, -1); refreshLists(); });
      down.addEventListener('click', async () => { await api.move_mod(i, 1); refreshLists(); });
      arrows.append(up, down);
      const c = el('label', 'check');
      const input = el('input'); input.type = 'checkbox'; input.checked = m.on;
      input.addEventListener('change', () => api.set_mod(m.name, input.checked));
      c.append(input, el('span', 'box'), el('span', null, m.name));
      row.append(el('span', 'num', `${i + 1}.`), arrows, c);
      mods.append(row);
    });
    if (r.mods.length > 1) mods.append(el('div', 'note', data.text.later_note));
    patches.replaceChildren();
    if (!r.patches.length) patches.append(el('div', 'note', r.no_patches));
    r.patches.forEach((p) => {
      const row = el('div', 'row');
      const c = el('label', 'check');
      const input = el('input'); input.type = 'checkbox'; input.checked = p.on;
      input.addEventListener('change', () => api.set_patch(p.key, input.checked));
      c.append(input, el('span', 'box'), el('span', null, p.key));
      row.append(c, el('span', 'author', p.author));
      patches.append(row);
    });
  }

  // ---- navigation and state ---------------------------------------------------------------------
  function show(id) {
    current = id;
    document.querySelectorAll('.page').forEach((p) => p.classList.toggle('active', p.id === `page-${id}`));
    document.querySelectorAll('#nav button').forEach((b) => b.classList.toggle('active', b.dataset.page === id));
    document.body.classList.toggle('with-art', id === 'play' && !!$('art').getAttribute('src'));
    if (id === 'mods') refreshLists();
    if (id === 'log') { const log = $('log'); log.scrollTop = log.scrollHeight; }
  }
  function setArt(url) {
    if (url) $('art').src = url; else $('art').removeAttribute('src');
    document.body.classList.toggle('with-art', current === 'play' && !!url);
  }

  function applyState(s) {
    lastState = s;
    const checks = $('checks');
    checks.replaceChildren();
    s.checks.forEach(([kind, text]) => {
      const li = el('li', kind);
      li.append(el('span', 'mark'), el('span', null, text));
      checks.append(li);
    });
    $('hero-sub').textContent = s.game;
    const status = $('status');
    status.textContent = s.status;
    status.classList.toggle('live', s.running);
    $('play').disabled = s.running || !s.can_play;
    $('stop').disabled = !s.running;
    document.querySelectorAll('[data-warn]').forEach((w) => { w.hidden = !s.warning; w.textContent = s.warning; });
    document.querySelectorAll('[data-fsr4]').forEach((b) => b.update(s.fsr4));
    const up = $('update');
    up.hidden = !s.update;
    if (s.update) $('update-text').textContent = s.update.state;
  }

  async function poll() {
    try {
      const r = await api.poll();
      if (r.log) appendLog(r.log);
      applyState(r.state);
    } catch (e) { /* the window is closing */ }
    setTimeout(poll, 300);
  }
  function appendLog(text) {
    const log = $('log');
    const atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 30;
    log.append(text);
    logLines += (text.match(/\n/g) || []).length;
    if (logLines > MAX_LOG) {
      const lines = log.textContent.split('\n');
      log.textContent = lines.slice(lines.length - MAX_LOG).join('\n');
      logLines = MAX_LOG;
    }
    if (atEnd) log.scrollTop = log.scrollHeight;
  }

  // ---- start ---------------------------------------------------------------------------------------
  async function start() {
    data = await api.init();
    document.documentElement.lang = data.lang;
    const t = data.text;
    $('by').textContent = t.by;
    $('sub').textContent = `${t.subtitle} · v${data.version}`;
    $('side-note').textContent = t.insert;
    $('ready-title').textContent = t.ready;
    $('quick-title').textContent = t.quick;
    $('play').querySelector('.play-label').textContent = t.play;
    $('stop').textContent = t.stop;
    $('log-copy').textContent = t.copy;
    $('log-clear').textContent = t.clear;
    $('update-install').textContent = t.update;
    $('update-news').textContent = t.whatsnew;

    const quick = $('quick');
    for (const item of data.quick) {
      if (item.t === 'check') { const c = check(item); c.classList.add('full'); quick.append(c); }
      else addRow(quick, item.label, item.t === 'slider' ? slider(item) : choice(item));
    }
    const pages = $('pages');
    data.pages.forEach((p) => pages.append(renderPage(p)));

    const nav = $('nav');
    data.state.nav.forEach(([id, title]) => {
      const b = el('button', null, title);
      b.dataset.page = id;
      b.addEventListener('click', () => show(id));
      nav.append(b);
      if (id === 'log') $('log-title').textContent = title;
    });

    Object.entries(data.values).forEach(([id, v]) => showValue(id, v));
    setArt(data.art);
    applyState(data.state);
    // After a language change the page reloads: come back to the page that was open.
    let page = 'play';
    try { page = sessionStorage.getItem('bb-page') || 'play'; sessionStorage.removeItem('bb-page'); } catch (e) { /* no storage */ }
    show(document.getElementById(`page-${page}`) ? page : 'play');

    $('play').addEventListener('click', async () => { $('play').disabled = true; result(await api.play()); });
    $('stop').addEventListener('click', () => api.stop());
    $('log-copy').addEventListener('click', () => navigator.clipboard.writeText($('log').textContent));
    $('log-clear').addEventListener('click', () => { $('log').textContent = ''; logLines = 0; });
    $('update-install').addEventListener('click', async () => result(await api.install_update()));
    $('update-news').addEventListener('click', () => api.whats_new());
    document.addEventListener('contextmenu', (e) => { if (!e.target.closest('input, #log')) e.preventDefault(); });
    $('app').classList.remove('loading');
    poll();
  }

  // ---- a stand-in API for a plain browser ----------------------------------------------------------
  function demoApi() {
    const opts = (a) => a.map((x) => [x, x]);
    const state = {
      checks: [['ok', 'Версия игры 01.09: доступны все патчи'], ['ok', 'Найдены сохранения в …\\user'],
        ['ok', 'Видеокарта: NVIDIA GeForce RTX 4060 Ti'], ['info', 'Нет ассетов FSR 4 («Графика»)']],
      warning: '', running: false, can_play: true, status: 'Без ограничения   ·   FSR 4   ·   2560 × 1440   ·   Офлайн',
      fsr4: { text: 'Установлены: 254 файла.', done: 254, total: 254, busy: false }, update: null,
      game: 'CUSA03173 · версия игры 01.09',
      nav: [['play', 'Играть'], ['graphics', 'Графика'], ['display', 'Экран и FPS'], ['controls', 'Управление'],
        ['game', 'Игра и эффекты'], ['cheats', 'Читы'], ['online', 'Онлайн-кооператив'], ['mods', 'Моды и патчи'],
        ['advanced', 'Дополнительно'], ['log', 'Журнал']],
    };
    const page = (id, title, items) => ({ id, title, subtitle: 'Хранится в bbport.ini; в игре меняется через меню (Insert).', items });
    return {
      init: async () => ({
        version: '2.1', lang: 'ru', art: null, state,
        text: { play: 'ИГРАТЬ', stop: 'Остановить', by: 'by giahoki', subtitle: 'нативный порт · Windows',
          insert: 'В игре: Insert открывает меню порта\n(геймпад: нажать оба стика).', ready: 'Проверка', quick: 'Основное',
          copy: 'Копировать', clear: 'Очистить', browse: 'Обзор…', open: 'Открыть', update: 'Обновить',
          whatsnew: 'Что нового', refresh: 'Обновить', checking: 'Проверка…', later_note: '' },
        quick: [
          { t: 'choice', key: 'fps_mode', store: 'app', label: 'Частота кадров', options: opts(['Без ограничения', '60 FPS', '90 FPS']) },
          { t: 'choice', key: 'upscaler', store: 'ini', label: 'Апскейлер', options: opts(['FSR 4 (лучшее качество)', 'DLSS', 'FSR 3.1']) },
          { t: 'choice', key: 'preset', store: 'ini', label: 'Пресет', options: opts(['Quality (×1.5)', 'Native AA']) },
          { t: 'choice', key: 'output_res', store: 'ini', label: 'Разрешение', options: opts(['2560 × 1440', '1920 × 1080']) },
          { t: 'slider', key: 'mouse_sensitivity', store: 'ini', label: 'Мышь', min: 0.1, max: 5, step: 0.05 },
          { t: 'check', key: 'fullscreen', store: 'app', label: 'Полный экран' },
          { t: 'check', key: 'online', store: 'app', label: 'Играть онлайн' },
        ],
        pages: [
          page('graphics', 'Графика', [{ t: 'section', label: 'Апскейлинг' },
            { t: 'choice', key: 'upscaler', store: 'ini', label: 'Апскейлер', options: opts(['FSR 4', 'DLSS']), hint: 'Временной апскейлинг с векторами движения игры.' },
            { t: 'check', key: 'sharpen', store: 'ini', label: 'Резкость (RCAS)' },
            { t: 'slider', key: 'sharpness', store: 'ini', label: 'Сила резкости', min: 0, max: 2, step: 0.05 }]),
          page('display', 'Экран и FPS', [{ t: 'warn' }]),
          page('controls', 'Управление', [{ t: 'section', label: 'Мышь' },
            { t: 'slider', key: 'mouse_sensitivity', store: 'ini', label: 'Чувствительность мыши', min: 0.1, max: 5, step: 0.05, hint: 'Мышь поворачивает камеру напрямую.' },
            { t: 'bindings', groups: [
              { title: 'Движение', actions: [{ key: 'key_move_forward', label: 'Вперёд', default: 'W' },
                { key: 'key_dodge_run', label: 'Уклонение / бег (удерживать)', default: 'Space' }] },
              { title: 'Бой', actions: [{ key: 'key_attack', label: 'Атака', default: 'Mouse1' },
                { key: 'key_strong_attack', label: 'Сильная атака', default: 'Shift+Mouse1|Mouse5' },
                { key: 'key_lock_on', label: 'Захват цели', default: 'Q|Mouse3' }] }] },
            { t: 'buttons', items: [['Сбросить по умолчанию', 'reset_keys']] }]),
          page('game', 'Игра и эффекты', [{ t: 'folder', key: 'game_dir', store: 'app', label: 'Папка игры' }]),
          page('cheats', 'Читы', []), page('online', 'Онлайн-кооператив', []),
          page('mods', 'Моды и патчи', [{ t: 'mods' }, { t: 'patches' }]), page('advanced', 'Дополнительно', []),
        ],
        values: { 'ini:mouse_sensitivity': 1.0, 'ini:sharpness': 0.5, 'ini:sharpen': true, 'app:fullscreen': false,
          'ini:key_move_forward': 'W', 'ini:key_dodge_run': 'Space', 'ini:key_attack': 'Mouse1',
          'ini:key_strong_attack': 'Shift+Mouse1|Mouse5', 'ini:key_lock_on': 'Q' },
      }),
      set: async () => ({ changed: {}, state }), poll: async () => ({ log: '', state }),
      lists: async () => ({ mods: [], patches: [], no_mods: 'Модов пока нет.', no_patches: 'Патчей пока нет.' }),
      play: async () => ({ info: 'Демо: игра не запускается в браузере.' }), stop: async () => null,
      browse: async () => null, open_path: async () => null, action: async () => null,
      test_connection: async () => 'Демо', download_fsr4: async () => null, install_update: async () => null,
      whats_new: async () => null, move_mod: async () => null, set_mod: async () => null, set_patch: async () => null,
    };
  }

  if (window.pywebview && window.pywebview.api) { api = window.pywebview.api; start(); }
  else {
    let started = false;
    window.addEventListener('pywebviewready', () => { if (!started) { started = true; api = window.pywebview.api; start(); } });
    setTimeout(() => { if (!started) { started = true; api = demoApi(); start(); } }, 1200);
  }
})();
