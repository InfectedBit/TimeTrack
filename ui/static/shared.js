/* ── TimeTrack shared logic — loaded by both index.html and apps.html ── */

// ── Themes ────────────────────────────────────────────────────────────────────
const THEMES = {
  synthwave:      { name:'Synthwave',   bg:'#0a0a0f', surface:'#111118', border:'#1e1e2e', accent:'#6366f1', accent2:'#a855f7', green:'#22d3ee', text:'#e2e8f0', muted:'#64748b', danger:'#f43f5e' },
  nord:           { name:'Nord',        bg:'#0f1117', surface:'#161b22', border:'#2d333b', accent:'#5e81ac', accent2:'#81a1c1', green:'#a3be8c', text:'#d8dee9', muted:'#5e6982', danger:'#bf616a' },
  gruvbox:        { name:'Gruvbox',     bg:'#1d2021', surface:'#282828', border:'#3c3836', accent:'#d79921', accent2:'#fe8019', green:'#98971a', text:'#ebdbb2', muted:'#a89984', danger:'#cc241d' },
  catppuccin:     { name:'Catppuccin',  bg:'#1e1e2e', surface:'#181825', border:'#313244', accent:'#cba6f7', accent2:'#f5c2e7', green:'#a6e3a1', text:'#cdd6f4', muted:'#585b70', danger:'#f38ba8' },
  midnight:       { name:'Midnight',    bg:'#000000', surface:'#0d0d0d', border:'#1a1a1a', accent:'#00ff87', accent2:'#00d4ff', green:'#00ff87', text:'#ffffff',  muted:'#666666', danger:'#ff4444' },
  'tokyo-night':  { name:'Tokyo Night', bg:'#1a1b26', surface:'#16161e', border:'#2a2b3d', accent:'#7aa2f7', accent2:'#bb9af7', green:'#9ece6a', text:'#c0caf5', muted:'#565f89', danger:'#f7768e' },
  dracula:        { name:'Dracula',     bg:'#282a36', surface:'#21222c', border:'#44475a', accent:'#bd93f9', accent2:'#ff79c6', green:'#50fa7b', text:'#f8f8f2', muted:'#6272a4', danger:'#ff5555' },
  monokai:        { name:'Monokai',     bg:'#272822', surface:'#1e1f1c', border:'#3e3d32', accent:'#f92672', accent2:'#66d9e8', green:'#a6e22e', text:'#f8f8f2', muted:'#75715e', danger:'#f92672' },
  'solarized-dark':{ name:'Solarized', bg:'#002b36', surface:'#073642', border:'#1b4a57', accent:'#268bd2', accent2:'#2aa198', green:'#859900', text:'#839496', muted:'#586e75', danger:'#dc322f' },
};

// ── Shared state ──────────────────────────────────────────────────────────────
let allProfiles = [];
let profileId   = null;
let hourFormat  = 'decimal';
let showImages  = true;
let _dismissedOpen = false;

// ── Utilities ─────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;');
}

async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${method} ${url} → ${res.status}`);
  return res.json();
}

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  return `${parseInt(h.slice(0,2),16)},${parseInt(h.slice(2,4),16)},${parseInt(h.slice(4,6),16)}`;
}

function fmtTime(s) {
  if (!s || s < 60) return `${s || 0}s`;
  if (s < 3600) return `${Math.floor(s/60)}m`;
  const h = Math.floor(s/3600), m = Math.floor((s % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function resolveImg(val) {
  if (!val) return '';
  if (val.startsWith('http://') || val.startsWith('https://')) return val;
  return '/user-images/' + val.split('/').pop();
}

// ── Preferences ───────────────────────────────────────────────────────────────
function getPrefs() {
  try { return JSON.parse(localStorage.getItem('tt_prefs') || '{}'); } catch { return {}; }
}
function savePrefs(patch) {
  localStorage.setItem('tt_prefs', JSON.stringify({ ...getPrefs(), ...patch }));
}

// ── Theme system ───────────────────────────────────────────────────────────────
function applyTheme(themeId, accentOverride) {
  const customs = getPrefs().custom_themes || [];
  const t = THEMES[themeId] || customs.find(c => c.id === themeId) || THEMES.synthwave;
  const r = document.documentElement;
  r.style.setProperty('--bg',      t.bg);
  r.style.setProperty('--surface', t.surface);
  r.style.setProperty('--border',  t.border);
  r.style.setProperty('--accent',  accentOverride || t.accent);
  r.style.setProperty('--accent2', t.accent2);
  r.style.setProperty('--green',   t.green);
  r.style.setProperty('--text',    t.text);
  r.style.setProperty('--muted',   t.muted);
  r.style.setProperty('--danger',  t.danger);
}

function renderThemeSwatches(activeTheme) {
  const el = document.getElementById('themeSwatches');
  if (!el) return;
  const presetHtml = Object.entries(THEMES).map(([id, t]) => `
    <div class="theme-swatch ${id === activeTheme ? 'active' : ''}" onclick="selectTheme('${id}')" title="${t.name}">
      <div class="theme-swatch-dots">
        <div class="theme-swatch-dot" style="background:${t.bg};border:1px solid ${t.border}"></div>
        <div class="theme-swatch-dot" style="background:${t.accent}"></div>
        <div class="theme-swatch-dot" style="background:${t.green}"></div>
      </div>
      <div class="theme-swatch-name">${t.name}</div>
    </div>`).join('');
  const customs = getPrefs().custom_themes || [];
  const customHtml = customs.length ? `
    <div class="theme-swatches-section-label">Custom</div>
    ${customs.map(t => `
      <div class="theme-swatch-wrap">
        <div class="theme-swatch ${t.id === activeTheme ? 'active' : ''}" onclick="selectTheme('${t.id}')" title="${esc(t.name)}">
          <div class="theme-swatch-dots">
            <div class="theme-swatch-dot" style="background:${t.bg};border:1px solid ${t.border}"></div>
            <div class="theme-swatch-dot" style="background:${t.accent}"></div>
            <div class="theme-swatch-dot" style="background:${t.green}"></div>
          </div>
          <div class="theme-swatch-name">${esc(t.name)}</div>
        </div>
        <button onclick="deleteCustomTheme('${t.id}')" title="Eliminar tema"
          style="position:absolute;top:-4px;right:-4px;width:16px;height:16px;border-radius:50%;
                 background:var(--danger);color:white;border:none;cursor:pointer;font-size:9px;
                 display:flex;align-items:center;justify-content:center;line-height:1">✕</button>
      </div>`).join('')}` : '';
  el.innerHTML = presetHtml + customHtml;
}

function selectTheme(themeId) {
  const prefs = getPrefs();
  savePrefs({ theme: themeId });
  applyTheme(themeId, prefs.accent_override);
  renderThemeSwatches(themeId);
  if (!prefs.accent_override) {
    const customs = prefs.custom_themes || [];
    const t = THEMES[themeId] || customs.find(c => c.id === themeId) || THEMES.synthwave;
    const ap = document.getElementById('accentPicker');
    const av = document.getElementById('accentValue');
    if (ap) ap.value = t.accent;
    if (av) av.textContent = t.accent;
  }
}

function onAccentChange(value) {
  const av = document.getElementById('accentValue');
  if (av) av.textContent = value;
  document.documentElement.style.setProperty('--accent', value);
  savePrefs({ accent_override: value });
}

function resetAccent() {
  savePrefs({ accent_override: null });
  const prefs = getPrefs();
  const themeId = prefs.theme || 'synthwave';
  const customs = prefs.custom_themes || [];
  const t = THEMES[themeId] || customs.find(c => c.id === themeId) || THEMES.synthwave;
  document.documentElement.style.setProperty('--accent', t.accent);
  const ap = document.getElementById('accentPicker');
  const av = document.getElementById('accentValue');
  if (ap) ap.value = t.accent;
  if (av) av.textContent = t.accent;
}

// ── Accent effects ────────────────────────────────────────────────────────────
function _accentMouseMove(e) {
  document.documentElement.style.setProperty('--mx', e.clientX + 'px');
  document.documentElement.style.setProperty('--my', e.clientY + 'px');
}

function applyAccentEffect(effect, accentColor) {
  let styleEl = document.getElementById('accent-fx');
  if (!styleEl) { styleEl = document.createElement('style'); styleEl.id = 'accent-fx'; document.head.appendChild(styleEl); }
  document.removeEventListener('mousemove', _accentMouseMove);
  if (!effect || effect.type === 'solid') { styleEl.textContent = ''; return; }
  const { type, target = 'app', colors = [], intensity = 0.6, speed = 1.0 } = effect;
  const col = accentColor || getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#6366f1';
  const rgb = hexToRgb(col), size = Math.round(intensity * 80), alpha = +(intensity * 0.6).toFixed(2);
  const appSels   = 'body, .sidebar';
  const modalSels = '.settings-modal, .day-modal, .detail-panel, .mini-modal';
  const sels = target === 'app' ? appSels : target === 'modals' ? modalSels : `${appSels}, ${modalSels}`;
  if (type === 'gradient') {
    const stops = colors.length >= 2 ? colors : [col, col];
    styleEl.textContent = `:root{--accent-g:linear-gradient(135deg,${stops.join(',')})}.btn-primary{background:var(--accent-g)!important}.profile-active-dot{background:var(--accent-g)!important}`;
  } else if (type === 'glow') {
    styleEl.textContent = `${sels}{box-shadow:inset 0 0 ${size}px rgba(${rgb},${+(alpha*.5).toFixed(2)})!important}${modalSels}{box-shadow:0 0 ${size}px rgba(${rgb},${alpha})!important}`;
  } else if (type === 'pulse') {
    styleEl.textContent = `@keyframes accent-pulse{0%,100%{box-shadow:0 0 ${Math.round(size*.4)}px rgba(${rgb},${+(alpha*.4).toFixed(2)})}50%{box-shadow:0 0 ${size}px rgba(${rgb},${alpha})}}${sels}{animation:accent-pulse ${speed}s ease-in-out infinite!important}`;
  } else if (type === 'breathe') {
    styleEl.textContent = `@keyframes accent-breathe{0%,100%{box-shadow:0 0 ${Math.round(size*.3)}px rgba(${rgb},${+(alpha*.3).toFixed(2)});opacity:.93}50%{box-shadow:0 0 ${size}px rgba(${rgb},${alpha});opacity:1}}${sels}{animation:accent-breathe ${+(speed*1.5).toFixed(1)}s ease-in-out infinite!important}`;
  } else if (type === 'wave') {
    styleEl.textContent = `@keyframes accent-wave{0%{box-shadow:-20px 0 ${size}px rgba(${rgb},${alpha})}50%{box-shadow:20px 0 ${size}px rgba(${rgb},${alpha})}100%{box-shadow:-20px 0 ${size}px rgba(${rgb},${alpha})}}${sels}{animation:accent-wave ${speed}s ease-in-out infinite!important}`;
  }
  if (['glow','pulse','breathe','wave'].includes(type) && target !== 'modals') {
    document.addEventListener('mousemove', _accentMouseMove);
  }
}

// ── Custom theme editor ───────────────────────────────────────────────────────
const _CE_VARS = [
  {v:'--bg',l:'BG'},{v:'--surface',l:'Surface'},{v:'--border',l:'Border'},
  {v:'--text',l:'Text'},{v:'--muted',l:'Muted'},{v:'--accent',l:'Accent'},
  {v:'--accent2',l:'Accent2'},{v:'--green',l:'Green'},{v:'--danger',l:'Danger'},
];

function buildCustomEditorGrid() {
  const grid = document.getElementById('customEditorGrid');
  if (!grid) return;
  grid.innerHTML = _CE_VARS.map(({v,l}) => `
    <div class="custom-editor-item">
      <input type="color" id="ce${v}" oninput="onCustomColorChange('${v}',this.value)">
      <label>${l}</label>
    </div>`).join('');
}

function resetCustomEditor() {
  const prefs = getPrefs();
  const t = THEMES[prefs.theme] || (prefs.custom_themes||[]).find(c=>c.id===prefs.theme) || THEMES.synthwave;
  const map = {'--bg':t.bg,'--surface':t.surface,'--border':t.border,'--text':t.text,
                '--muted':t.muted,'--accent':t.accent,'--accent2':t.accent2,'--green':t.green,'--danger':t.danger};
  _CE_VARS.forEach(({v}) => { const el=document.getElementById(`ce${v}`); if(el) el.value=map[v]||'#000000'; });
}

function onCustomColorChange(varName, value) {
  document.documentElement.style.setProperty(varName, value);
  if (varName === '--accent') {
    const ap=document.getElementById('accentPicker'), av=document.getElementById('accentValue');
    if(ap) ap.value=value; if(av) av.textContent=value;
  }
}

function saveCustomTheme() {
  const name=(document.getElementById('customThemeName').value||'').trim();
  if(!name){alert('Escribe un nombre para el tema.');return;}
  const get=v=>(document.getElementById(`ce${v}`)||{}).value||'#000000';
  const theme={id:'ct_'+Date.now(),name,bg:get('--bg'),surface:get('--surface'),border:get('--border'),
                text:get('--text'),muted:get('--muted'),accent:get('--accent'),
                accent2:get('--accent2'),green:get('--green'),danger:get('--danger')};
  const prefs=getPrefs(), customs=prefs.custom_themes||[];
  customs.push(theme);
  savePrefs({custom_themes:customs,theme:theme.id});
  applyTheme(theme.id);
  renderThemeSwatches(theme.id);
  document.getElementById('customThemeName').value='';
}

function deleteCustomTheme(id) {
  const prefs=getPrefs(), customs=(prefs.custom_themes||[]).filter(t=>t.id!==id);
  const newTheme=prefs.theme===id?'synthwave':(prefs.theme||'synthwave');
  savePrefs({custom_themes:customs,theme:newTheme});
  if(prefs.theme===id) applyTheme('synthwave');
  renderThemeSwatches(getPrefs().theme||'synthwave');
}

// ── Settings modal ─────────────────────────────────────────────────────────────
function switchSettingsTab(btn) {
  document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  const tab = btn.dataset.tab;
  ['tabVisual','tabTracker','tabArte','tabProfiles'].forEach(id => {
    const el = document.getElementById(id);
    if(el) el.style.display = id === 'tab' + tab.charAt(0).toUpperCase() + tab.slice(1) ? '' : 'none';
  });
}

function toggleInfo(wrap) {
  wrap.classList.toggle('open');
  document.addEventListener('click', function handler(e) {
    if(!wrap.contains(e.target)) { wrap.classList.remove('open'); document.removeEventListener('click', handler); }
  }, { capture: true, once: false });
}

async function applyArtToAll() {
  const btn = document.getElementById('applyAllBtn');
  if(btn) { btn.disabled = true; btn.textContent = '⏳ Buscando…'; }
  try {
    await api(`/api/profiles/${profileId}/images/auto-fetch-all`, 'POST');
    if(btn) btn.textContent = '✓ Buscando en background…';
    setTimeout(() => { if(btn) { btn.disabled = false; btn.textContent = '🎨 Aplicar a todas las apps del perfil'; }}, 3000);
  } catch(e) {
    if(btn) { btn.disabled = false; btn.textContent = '🎨 Aplicar a todas las apps del perfil'; }
    alert('Error: ' + e.message);
  }
}

async function openSettings() {
  const prefs = getPrefs();
  // Visual tab
  const mode = prefs.detail_mode || 'panel';
  document.querySelectorAll('.mode-opt').forEach(btn => btn.classList.toggle('selected', btn.dataset.mode === mode));
  renderThemeSwatches(prefs.theme || 'synthwave');
  const accentVal = prefs.accent_override || getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  const ap=document.getElementById('accentPicker'), av=document.getElementById('accentValue');
  if(ap) ap.value=accentVal; if(av) av.textContent=accentVal;
  document.querySelectorAll('#hourFmtOpts .fmt-opt').forEach(b =>
    b.classList.toggle('selected', b.dataset.fmt === (prefs.hourFormat||'decimal')));
  const cuDI=document.getElementById('casualUseDaysInput');     if(cuDI) cuDI.value=prefs.casualUseDays??7;
  const itDI=document.getElementById('inactivityTailDaysInput'); if(itDI) itDI.value=prefs.inactivityTailDays??14;
  const pmI =document.getElementById('pointMinMinutesInput');    if(pmI)  pmI.value =prefs.pointMinMinutes??1;
  document.querySelectorAll('#tabVisual > details.settings-section').forEach(d => { d.open=true; });
  const ceD=document.getElementById('customEditorDetails'); if(ceD) ceD.open=false;
  // Tracker tab
  try {
    const s = await api('/api/settings');
    const gdt=document.getElementById('gameDetectToggle');  if(gdt) gdt.checked=!!s.game_detect;
    const gdm=document.getElementById('gameDetectMain');    if(gdm) gdm.checked=!!s.game_detect;
    const sit=document.getElementById('showImagesToggle');  if(sit) sit.checked=!!s.show_app_images;
    const aft=document.getElementById('autoFetchToggle');   if(aft) aft.checked=!!s.auto_fetch_images;
    // Key inputs: fill value and reset to hidden (password) state
    ['sgdbKeyInput','rawgKeyInput'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.value = id === 'sgdbKeyInput' ? (s.sgdb_api_key||'') : (s.rawg_api_key||'');
      el.type = 'password';
      const btn = el.nextElementSibling;
      if (btn && btn.classList.contains('btn-eye')) { btn.classList.remove('hidden-state'); btn.title = 'Mostrar key'; }
    });
    document.querySelectorAll('#notifModeOpts .fmt-opt').forEach(b =>
      b.classList.toggle('selected', b.dataset.mode===(s.notification_mode||'tray')));
    renderDetectMethods(s.detect_methods||[]);
    const dismissed=await api('/api/dismissed-games');
    updateDismissedCount(dismissed.length);
    if(_dismissedOpen) await loadDismissedList();
    loadGamePaths();
  } catch(_){}
  loadProfilesSettings();
  switchSettingsTab(document.querySelector('.settings-tab[data-tab="visual"]'));
  document.getElementById('settingsModal').classList.add('open');
}

function closeSettings() {
  document.getElementById('settingsModal').classList.remove('open');
  document.querySelectorAll('.info-wrap.open').forEach(w => w.classList.remove('open'));
}

function selectMode(btn) {
  document.querySelectorAll('.mode-opt').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  savePrefs({ detail_mode: btn.dataset.mode });
}

function setHourFormat(fmt) {
  hourFormat = fmt;
  savePrefs({ hourFormat: fmt });
  document.querySelectorAll('#hourFmtOpts .fmt-opt').forEach(b =>
    b.classList.toggle('selected', b.dataset.fmt === fmt));
  // Chart updates: override in index.html if needed
}

function setCasualUseDays(v) {
  if(!v||v<1) return;
  savePrefs({casualUseDays:v});
  if(typeof _buildLineChart==='function') _buildLineChart();
}

function setInactivityTailDays(v) {
  if(!v||v<1) return;
  savePrefs({inactivityTailDays:v});
  if(typeof _buildLineChart==='function') _buildLineChart();
}

function setPointMinMinutes(v) {
  if(v<0) return;
  savePrefs({pointMinMinutes:v});
  if(typeof _buildLineChart==='function') _buildLineChart();
}

async function setShowImages(enabled) {
  showImages = enabled;
  await api('/api/settings', 'POST', { show_app_images: enabled });
  if(typeof renderSummary==='function') renderSummary(typeof lastSummary!=='undefined'?lastSummary:[]);
  if(typeof renderApps==='function') renderApps();
  const bannerEl=document.getElementById('detailBanner');
  if(bannerEl && typeof detailApp!=='undefined' && detailApp) {
    const bImg=document.getElementById('detailBannerImg');
    if(showImages && detailApp.img_banner) { if(bImg) bImg.src=resolveImg(detailApp.img_banner); bannerEl.style.display=''; }
    else bannerEl.style.display='none';
  }
  // Update art-disabled hints on both pages
  const hint   = document.getElementById('artDisabledHint');
  if (hint)   hint.style.display   = enabled ? 'none' : '';
  const notice = document.getElementById('artDisabledNotice');
  if (notice) notice.style.display = enabled ? 'none' : '';
}

function openSettingsArt() {
  openSettings();
  setTimeout(() => {
    switchSettingsTab(document.querySelector('.settings-tab[data-tab="arte"]'));
    document.getElementById('showImagesToggle')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 120);
}

// ── Image auto-fetch settings ─────────────────────────────────────────────────
async function setAutoFetchImages(enabled) {
  await api('/api/settings', 'POST', { auto_fetch_images: enabled });
}

async function saveApiKey(keyName, value) {
  await api('/api/settings', 'POST', { [keyName]: value.trim() });
}

function toggleKeyVisibility(btn) {
  const input = btn.previousElementSibling;
  if (!input) return;
  const reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  btn.classList.toggle('hidden-state', reveal);
  btn.title = reveal ? 'Ocultar key' : 'Mostrar key';
}

// ── Game detection ─────────────────────────────────────────────────────────────
async function setGameDetect(enabled) {
  const status=await api('/api/tracker/status');
  await api('/api/tracker/settings','POST',{auto_detect:status.auto_detect,game_detect:enabled});
  const gdt=document.getElementById('gameDetectToggle'); if(gdt) gdt.checked=enabled;
  const gdm=document.getElementById('gameDetectMain');   if(gdm) gdm.checked=enabled;
}

async function setNotifMode(mode) {
  await api('/api/settings','POST',{notification_mode:mode});
  document.querySelectorAll('#notifModeOpts .fmt-opt').forEach(b =>
    b.classList.toggle('selected', b.dataset.mode===mode));
}

async function clearDismissed() {
  await api('/api/dismissed-games','DELETE');
  updateDismissedCount(0);
  if(_dismissedOpen) await loadDismissedList();
}

function updateDismissedCount(count) {
  const txt = count ? `${count} entrada(s)` : '';
  ['dismissedCount','dismissedCount_main'].forEach(id => { const el=document.getElementById(id); if(el) el.textContent=txt; });
}

async function toggleDismissedList() {
  const el=document.getElementById('dismissedList'), btn=document.getElementById('dismissedToggleBtn');
  _dismissedOpen=!_dismissedOpen;
  if(_dismissedOpen) { if(el) el.style.display='flex'; if(btn) btn.textContent='▲ Ocultar lista'; await loadDismissedList(); }
  else               { if(el) el.style.display='none'; if(btn) btn.textContent='👁 Ver lista'; }
}

let _dismissedOpenMain = false;
async function toggleDismissedListMain() {
  const el=document.getElementById('dismissedList_main'), btn=document.getElementById('dismissedToggleBtn_main');
  _dismissedOpenMain=!_dismissedOpenMain;
  if(_dismissedOpenMain) { if(el) el.style.display='flex'; if(btn) btn.textContent='▲ Ocultar'; await loadDismissedList(); }
  else                   { if(el) el.style.display='none'; if(btn) btn.textContent='👁 Ver lista'; }
}

async function loadDismissedList() {
  const items=await api('/api/dismissed-games');
  updateDismissedCount(items.length);
  const html = items.length
    ? items.map(exe=>`
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;
          background:var(--surface2,rgba(255,255,255,.04));border-radius:5px;padding:4px 8px;
          font-family:var(--mono);font-size:11px">
          <span style="color:var(--text);word-break:break-all">${esc(exe)}</span>
          <button class="btn btn-ghost btn-sm" onclick="undismiss('${esc(exe)}')"
            style="padding:2px 6px;flex-shrink:0;line-height:1">✕</button>
        </div>`).join('')
    : '<div style="font-size:11px;color:var(--muted);font-family:var(--mono)">Lista vacía.</div>';
  const el=document.getElementById('dismissedList');       if(el && _dismissedOpen)     el.innerHTML=html;
  const em=document.getElementById('dismissedList_main');  if(em && _dismissedOpenMain) em.innerHTML=html;
}

async function undismiss(exe) {
  await api(`/api/dismissed-games/${encodeURIComponent(exe)}`,'DELETE');
  await loadDismissedList();
}

// ── Detection methods ─────────────────────────────────────────────────────────
const DETECT_METHODS = [
  {id:'launcher',  label:'Launcher paths (Steam, Epic, GOG, Ubisoft…)'},
  {id:'custom',    label:'Rutas personalizadas'},
  {id:'gamemode',  label:'Windows Game Mode (registro)'},
  {id:'nvidia',    label:'Perfiles NVIDIA DRS'},
  {id:'heuristic', label:'Heurística (palabras clave en ruta)'},
];

function renderDetectMethods(enabled) {
  const html=DETECT_METHODS.map(m=>`
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
      <input type="checkbox" ${enabled.includes(m.id)?'checked':''} onchange="toggleDetectMethod('${m.id}',this.checked)" style="width:14px;height:14px;cursor:pointer">
      ${m.label}
    </label>`).join('');
  ['detectMethodsList','detectMethodsList_main'].forEach(id => { const el=document.getElementById(id); if(el) el.innerHTML=html; });
}

async function toggleDetectMethod(method, checked) {
  const s=await api('/api/settings');
  let methods=s.detect_methods||[];
  if(checked){ if(!methods.includes(method)) methods.push(method); }
  else methods=methods.filter(m=>m!==method);
  await api('/api/settings','POST',{detect_methods:methods});
}

// ── Game paths ────────────────────────────────────────────────────────────────
async function loadGamePaths() {
  const paths=await api('/api/game-paths');
  const html=paths.length
    ? paths.map(p=>`
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;
          background:var(--bg);border:1px solid var(--border);border-radius:5px;padding:4px 8px;font-family:var(--mono);font-size:11px">
          <span style="word-break:break-all;color:var(--text)">${esc(p.path)}</span>
          <button class="btn btn-ghost btn-sm" onclick="removeGamePath(${p.id})" style="padding:2px 6px;flex-shrink:0;line-height:1">✕</button>
        </div>`).join('')
    : '<div style="font-size:11px;color:var(--muted);font-family:var(--mono)">Sin rutas añadidas.</div>';
  ['gamePathsList','gamePathsList_main'].forEach(id => { const el=document.getElementById(id); if(el) el.innerHTML=html; });
}

async function addGamePath() {
  const input=document.getElementById('gamePathInput');
  const path=input?.value.trim(); if(!path) return;
  await api('/api/game-paths','POST',{path});
  input.value='';
  loadGamePaths();
}

async function addGamePathMain() {
  const input=document.getElementById('gamePathInput_main');
  const path=input?.value.trim(); if(!path) return;
  await api('/api/game-paths','POST',{path});
  input.value='';
  loadGamePaths();
}

async function removeGamePath(id) {
  await api(`/api/game-paths/${id}`,'DELETE');
  loadGamePaths();
}

// ── Profile management ────────────────────────────────────────────────────────
function loadProfilesSettings() {
  const listEl=document.getElementById('profilesList');
  const fromSel=document.getElementById('migrateFrom'), toSel=document.getElementById('migrateTo');
  const expSel=document.getElementById('exportProfile');
  if(listEl) listEl.innerHTML=allProfiles.map(p=>`
    <div class="profile-list-item ${p.is_active?'is-active':''}">
      <div class="profile-item-name">
        ${p.is_active?'<div class="profile-active-dot"></div>':''}
        ${esc(p.name)}
      </div>
      <div class="profile-item-btns">
        ${!p.is_active?`<button class="btn-ghost" style="font-size:11px;padding:4px 10px" onclick="activateProfile(${p.id})">● Activate</button>`:''}
        ${p.name!=='Default'?`<button class="btn-danger btn-sm" onclick="deleteProfile(${p.id})">✕</button>`:''}
      </div>
    </div>`).join('');
  const opts=allProfiles.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');
  if(fromSel) fromSel.innerHTML=opts; if(toSel) toSel.innerHTML=opts; if(expSel) expSel.innerHTML=opts;
  if(allProfiles.length>=2 && fromSel && toSel){ fromSel.selectedIndex=0; toSel.selectedIndex=1; }
}

async function newProfile() {
  const name=prompt('Profile name:');
  if(!name?.trim()) return;
  await api('/api/profiles','POST',{name:name.trim()});
  if(typeof loadProfiles==='function') { await loadProfiles(); loadProfilesSettings(); }
  if(typeof loadApps==='function') await loadApps();
  if(typeof dataRefresh==='function') dataRefresh();
}

async function activateProfile(id) {
  await fetch(`/api/profiles/${id}/activate`,{method:'PUT'});
  profileId=id;
  if(typeof loadProfiles==='function') { await loadProfiles(); loadProfilesSettings(); }
  if(typeof loadApps==='function') await loadApps();
  if(typeof closeDetail==='function') closeDetail();
  if(typeof dataRefresh==='function') dataRefresh();
}

async function deleteProfile(id) {
  if(!confirm('Delete this profile and all its data?')) return;
  await api(`/api/profiles/${id}`,'DELETE');
  if(typeof loadProfiles==='function') { await loadProfiles(); loadProfilesSettings(); }
  if(typeof loadApps==='function') await loadApps();
  if(typeof dataRefresh==='function') dataRefresh();
}

async function confirmMigrate() {
  const fromId=parseInt(document.getElementById('migrateFrom').value);
  const toId=parseInt(document.getElementById('migrateTo').value);
  if(fromId===toId){alert('Source and destination must be different.');return;}
  const fromName=allProfiles.find(p=>p.id===fromId)?.name||fromId;
  const toName=allProfiles.find(p=>p.id===toId)?.name||toId;
  if(!confirm(`Move all data from "${fromName}" → "${toName}"? This cannot be undone.`)) return;
  await api('/api/profiles/migrate','POST',{from_id:fromId,to_id:toId});
  alert('Migration complete.');
  if(typeof loadProfiles==='function') { await loadProfiles(); loadProfilesSettings(); }
  if(typeof loadApps==='function') await loadApps();
  if(typeof dataRefresh==='function') dataRefresh();
}

function doExportProfile() {
  const id=parseInt(document.getElementById('exportProfile').value);
  window.location.href=`/api/profiles/${id}/export`;
}

async function importProfileFile(input) {
  if(!input.files||!input.files[0]) return;
  const statusEl = document.getElementById('importStatus');
  if(statusEl) statusEl.textContent = 'Importando…';
  const formData = new FormData();
  formData.append('file', input.files[0]);
  try {
    const res = await fetch('/api/profiles/import', { method:'POST', body: formData });
    let raw={}; try{raw=await res.json();}catch{}
    if(!res.ok) {
      const msg = typeof raw.detail==='string' ? raw.detail : JSON.stringify(raw.detail||raw);
      alert('Error al importar: '+msg);
      if(statusEl) statusEl.textContent='';
      return;
    }
    if(statusEl) statusEl.textContent = `✓ "${raw.name}" — ${raw.apps_imported} apps, ${raw.sessions_imported} sesiones`;
    if(typeof loadProfiles==='function') { await loadProfiles(); loadProfilesSettings(); }
    if(typeof dataRefresh==='function') dataRefresh();
    if(typeof loadApps==='function') await loadApps();
  } catch(e) {
    alert('Error de red: '+e.message);
    if(statusEl) statusEl.textContent='';
  }
  input.value = '';
}

// ── Sidebar resource bar ───────────────────────────────────────────────────────
async function pollResources() {
  try {
    const s=await api('/api/tracker/status');
    const cpu=document.getElementById('resCpu'), mem=document.getElementById('resMem');
    if(cpu) cpu.textContent=(s.cpu_pct??0)+'%';
    if(mem) mem.textContent=(s.mem_mb??0)+' MB';
    const st=document.getElementById('trackerStatus');
    if(st) {
      if(s.paused)       { st.textContent='⏸ paused';  st.style.color='#a855f7'; }
      else if(s.running) { st.textContent='● running'; st.style.color='var(--green)'; }
      else               { st.textContent='○ stopped'; st.style.color='var(--muted)'; }
    }
  } catch {
    const st=document.getElementById('trackerStatus');
    if(st){ st.textContent='○ offline'; st.style.color='var(--muted)'; }
  }
}

// ── Shared init (call from each page's init()) ────────────────────────────────
function initShared() {
  const prefs=getPrefs();
  hourFormat=prefs.hourFormat||'decimal';
  applyTheme(prefs.theme||'synthwave', prefs.accent_override);
  const fx=document.getElementById('accent-fx'); if(fx) fx.textContent='';
}

// ── Settings modal HTML (single source of truth) ─────────────────────────────
function _buildSettingsModal() {
  const hasCharts = !!window._settingsHasCharts;
  return `
<div class="modal-bg" id="settingsModal" onclick="if(event.target===this)closeSettings()">
  <div class="settings-modal">
    <div class="modal-head">
      <h3>⚙ Settings</h3>
      <button class="modal-close" onclick="closeSettings()">×</button>
    </div>
    <div class="settings-tabs">
      <button class="settings-tab active" data-tab="visual"   onclick="switchSettingsTab(this)">Visual</button>
      <button class="settings-tab"        data-tab="tracker"  onclick="switchSettingsTab(this)">Tracker</button>
      <button class="settings-tab"        data-tab="arte"     onclick="switchSettingsTab(this)">Arte</button>
      <button class="settings-tab"        data-tab="profiles" onclick="switchSettingsTab(this)">Profiles</button>
    </div>

    <!-- Tab: Visual -->
    <div class="settings-body" id="tabVisual">

      <details class="settings-section" open>
        <summary><span class="section-title">Vista de detalle de app</span><span class="section-arrow">▶</span></summary>
        <div class="section-body">
          <div class="mode-opts" id="modeOpts">
            <button class="mode-opt" data-mode="panel" onclick="selectMode(this)">
              <div class="mode-opt-radio"></div>
              <div>
                <span class="mode-opt-label">Panel lateral</span>
                <span class="mode-opt-sub">Desliza desde la derecha — vista clásica</span>
              </div>
            </button>
            <button class="mode-opt" data-mode="modal" onclick="selectMode(this)">
              <div class="mode-opt-radio"></div>
              <div>
                <span class="mode-opt-label">Modal centrado</span>
                <span class="mode-opt-sub">Ventana centrada sobre el dashboard</span>
              </div>
            </button>
            <button class="mode-opt" data-mode="float" onclick="selectMode(this)">
              <div class="mode-opt-radio"></div>
              <div>
                <span class="mode-opt-label">Flotante</span>
                <span class="mode-opt-sub">Ventana arrastrable libre — sin overlay</span>
              </div>
            </button>
          </div>
        </div>
      </details>

      <details class="settings-section" open>
        <summary><span class="section-title">Color theme</span><span class="section-arrow">▶</span></summary>
        <div class="section-body">
          <div class="theme-swatches" id="themeSwatches"></div>
          <details class="settings-sub" open>
            <summary><span class="sub-title">Accent color</span><span class="section-arrow">▶</span></summary>
            <div class="section-body" style="padding-top:10px">
              <div style="display:flex;align-items:center;gap:10px">
                <input type="color" id="accentPicker" oninput="onAccentChange(this.value)">
                <span style="font-family:var(--mono);font-size:11px;color:var(--muted)" id="accentValue">#6366f1</span>
                <button class="btn-ghost" style="font-size:11px;padding:4px 10px" onclick="resetAccent()">Reset</button>
              </div>
            </div>
          </details>
          <details class="settings-sub" id="customEditorDetails"
                   ontoggle="if(this.open){buildCustomEditorGrid();resetCustomEditor();}">
            <summary><span class="sub-title">Custom theme editor</span><span class="section-arrow">▶</span></summary>
            <div class="section-body" style="padding-top:10px">
              <div class="custom-editor-grid" id="customEditorGrid"></div>
              <div style="display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap">
                <input type="text" id="customThemeName" placeholder="Nombre del tema"
                  style="background:var(--surface);border:1px solid var(--border);color:var(--text);
                         padding:6px 10px;border-radius:7px;font-family:var(--mono);font-size:12px;
                         outline:none;flex:1;min-width:120px">
                <button class="btn-primary btn-sm" onclick="saveCustomTheme()">Guardar tema</button>
                <button class="btn-ghost btn-sm" onclick="resetCustomEditor()">Resetear</button>
              </div>
            </div>
          </details>
        </div>
      </details>

      <details class="settings-section" open>
        <summary><span class="section-title">Hour format in charts</span><span class="section-arrow">▶</span></summary>
        <div class="section-body">
          <div style="display:flex;gap:8px" id="hourFmtOpts">
            <button class="fmt-opt" data-fmt="decimal" onclick="setHourFormat('decimal')">1.5h</button>
            <button class="fmt-opt" data-fmt="human"   onclick="setHourFormat('human')">1h30m</button>
          </div>
        </div>
      </details>

      ${hasCharts ? `
      <details class="settings-section" open>
        <summary><span class="section-title">Uso en gráficas</span><span class="section-arrow">▶</span></summary>
        <div class="section-body" style="display:flex;flex-direction:column;gap:16px">
          <div>
            <div style="display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:12px;flex-wrap:wrap">
              <span style="color:var(--muted)">App con 1 uso → solo punto si lleva más de</span>
              <input type="number" id="casualUseDaysInput" min="1" max="365" value="7"
                style="width:52px;background:var(--surface2,rgba(255,255,255,.04));border:1px solid var(--border);
                       border-radius:6px;padding:4px 6px;color:var(--text);font-family:var(--mono);
                       font-size:12px;text-align:center"
                onchange="setCasualUseDays(+this.value)">
              <span style="color:var(--muted)">días sin actividad</span>
            </div>
            <div style="font-size:10px;color:var(--muted);margin-top:4px;font-family:var(--mono)">
              Apps de un solo uso aparecen como punto en vez de línea con ceros.
            </div>
          </div>
          <div>
            <div style="display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:12px;flex-wrap:wrap">
              <span style="color:var(--muted)">Mostrar</span>
              <input type="number" id="inactivityTailDaysInput" min="1" max="365" value="14"
                style="width:52px;background:var(--surface2,rgba(255,255,255,.04));border:1px solid var(--border);
                       border-radius:6px;padding:4px 6px;color:var(--text);font-family:var(--mono);
                       font-size:12px;text-align:center"
                onchange="setInactivityTailDays(+this.value)">
              <span style="color:var(--muted)">días de ceros antes/después de actividad</span>
            </div>
            <div style="font-size:10px;color:var(--muted);margin-top:4px;font-family:var(--mono)">
              Extiende la línea X días antes y después de la actividad para ver periodos de inactividad.
            </div>
          </div>
          <div>
            <div style="display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:12px;flex-wrap:wrap">
              <span style="color:var(--muted)">Ocultar punto si el uso es menor de</span>
              <input type="number" id="pointMinMinutesInput" min="0" max="60" value="1"
                style="width:52px;background:var(--surface2,rgba(255,255,255,.04));border:1px solid var(--border);
                       border-radius:6px;padding:4px 6px;color:var(--text);font-family:var(--mono);
                       font-size:12px;text-align:center"
                onchange="setPointMinMinutes(+this.value)">
              <span style="color:var(--muted)">minutos</span>
            </div>
            <div style="font-size:10px;color:var(--muted);margin-top:4px;font-family:var(--mono)">
              En gráfica horaria y diaria, los puntos por debajo del umbral no se muestran (la línea se mantiene).
            </div>
          </div>
        </div>
      </details>` : ''}

    </div>

    <!-- Tab: Tracker -->
    <div class="settings-body" id="tabTracker" style="display:none">
      <div>
        <div class="setting-group-label">Detección de juegos</div>
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-family:var(--mono);font-size:12px">
          <input type="checkbox" id="gameDetectToggle" onchange="setGameDetect(this.checked)" style="width:16px;height:16px;cursor:pointer">
          Detectar juegos automáticamente (con confirmación)
        </label>
        <div style="font-size:10px;color:var(--muted);margin-top:4px;font-family:var(--mono)">
          Detecta Steam, Epic, GOG, Ubisoft, Xbox y más — sin añadir nada sin tu permiso.
        </div>
      </div>
      <div>
        <div class="setting-group-label">Tipo de notificación</div>
        <div style="display:flex;gap:8px" id="notifModeOpts">
          <button class="fmt-opt" data-mode="tray"  onclick="setNotifMode('tray')">Tray menu</button>
          <button class="fmt-opt" data-mode="toast" onclick="setNotifMode('toast')">Windows Toast</button>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:4px;font-family:var(--mono)">
          Toast requiere <code>win11toast</code> instalado.
        </div>
      </div>
      <div>
        <div class="setting-group-label">Lista "No preguntar más"</div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" onclick="clearDismissed()">✕ Limpiar lista</button>
          <button class="btn btn-ghost btn-sm" id="dismissedToggleBtn" onclick="toggleDismissedList()">👁 Ver lista</button>
          <span style="font-size:10px;color:var(--muted);font-family:var(--mono)" id="dismissedCount"></span>
        </div>
        <div id="dismissedList" style="display:none;flex-direction:column;gap:4px;margin-top:8px;max-height:180px;overflow-y:auto"></div>
      </div>
      <div>
        <div class="setting-group-label">Métodos de detección</div>
        <div id="detectMethodsList" style="display:flex;flex-direction:column;gap:6px;font-family:var(--mono);font-size:12px"></div>
      </div>
      <div>
        <div class="setting-group-label">Rutas personalizadas</div>
        <div id="gamePathsList" style="display:flex;flex-direction:column;gap:4px;margin-bottom:8px;max-height:160px;overflow-y:auto"></div>
        <div style="display:flex;gap:6px">
          <input type="text" id="gamePathInput" placeholder="M:\\MRGames"
            style="flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:6px;
                   padding:6px 8px;color:var(--text);font-family:var(--mono);font-size:11px"
            onkeydown="if(event.key==='Enter')addGamePath()">
          <button class="btn btn-primary btn-sm" onclick="addGamePath()">+ Añadir</button>
        </div>
      </div>
    </div>

    <!-- Tab: Arte -->
    <div class="settings-body" id="tabArte" style="display:none">

      <!-- Master artwork toggle -->
      <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0 20px;border-bottom:1px solid var(--border);margin-bottom:4px">
        <div>
          <div style="font-family:var(--mono);font-size:13px;font-weight:700;color:var(--text)">Mostrar arte</div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:3px">
            Iconos, banners y pósters en cards y paneles.<br>Los archivos descargados se conservan al desactivar.
          </div>
        </div>
        <label class="toggle" style="flex-shrink:0">
          <input type="checkbox" id="showImagesToggle" onchange="setShowImages(this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>

      <details class="settings-section" open>
        <summary><span class="section-title">Búsqueda automática</span><span class="section-arrow">▶</span></summary>
        <div class="section-body">
          <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-family:var(--mono);font-size:12px;margin-bottom:10px">
            <input type="checkbox" id="autoFetchToggle" onchange="setAutoFetchImages(this.checked)" style="width:16px;height:16px;cursor:pointer">
            Auto-fetch al añadir una nueva app
          </label>
          <button class="arte-apply-btn" id="applyAllBtn" onclick="applyArtToAll()">
            🎨 Aplicar a todas las apps del perfil
          </button>
          <div style="font-size:10px;color:var(--muted);font-family:var(--mono);margin-top:6px">
            Ejecuta la búsqueda en todas las apps activas en segundo plano.
          </div>
        </div>
      </details>

      <details class="settings-section">
        <summary>
          <span style="display:flex;align-items:center;gap:8px">
            <span class="section-title">Steam CDN</span>
            <span class="arte-source-badge free">Sin API key</span>
          </span>
          <span class="section-arrow">▶</span>
        </summary>
        <div class="section-body">
          <div style="font-family:var(--mono);font-size:11px;color:var(--muted)">
            Banner y póster para juegos de Steam. Detecta el App ID leyendo los ficheros .acf de las librerías de Steam instaladas.
          </div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:4px">🎯 Steam &nbsp;·&nbsp; 🖼 Banner, Póster</div>
        </div>
      </details>

      <details class="settings-section" open>
        <summary>
          <span style="display:flex;align-items:center;gap:8px">
            <span class="section-title">SteamGridDB</span>
            <span class="arte-source-badge free-key">API key gratuita</span>
          </span>
          <span class="section-arrow">▶</span>
        </summary>
        <div class="section-body">
          <div style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-bottom:8px">
            Arte comunitario: Steam, GOG, Epic, indie, emuladores.
            <span style="display:block;margin-top:2px">🎯 Todos los juegos &nbsp;·&nbsp; 🖼 Banner, Icono</span>
          </div>
          <div class="arte-key-row">
            <input type="password" id="sgdbKeyInput" class="arte-key-input" placeholder="••••••••••••••••••••"
              autocomplete="new-password" onblur="saveApiKey('sgdb_api_key', this.value)">
            <button class="btn-eye" type="button" title="Mostrar key" onclick="toggleKeyVisibility(this)">👁</button>
            <div class="info-wrap" onclick="toggleInfo(this)">
              <button class="info-btn" type="button">?</button>
              <div class="info-popup">
                <strong>Cómo obtener la key:</strong>
                <ol style="margin-top:6px">
                  <li>Ve a <strong>steamgriddb.com</strong></li>
                  <li>Crea una cuenta gratuita</li>
                  <li>Perfil → <strong>Preferences</strong></li>
                  <li>Sección <strong>API</strong> → Generate key</li>
                  <li>Copia y pega la key aquí</li>
                </ol>
              </div>
            </div>
          </div>
          <a href="https://www.steamgriddb.com/profile/preferences/api" target="_blank" class="arte-key-link" style="margin-top:6px;display:inline-block">steamgriddb.com ↗</a>
        </div>
      </details>

      <details class="settings-section" open>
        <summary>
          <span style="display:flex;align-items:center;gap:8px">
            <span class="section-title">RAWG</span>
            <span class="arte-source-badge free-key">API key gratuita</span>
          </span>
          <span class="section-arrow">▶</span>
        </summary>
        <div class="section-body">
          <div style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-bottom:8px">
            Base de datos de 500k+ juegos.
            <span style="display:block;margin-top:2px">🎯 PC, consolas, indie &nbsp;·&nbsp; 🖼 Banner</span>
          </div>
          <div class="arte-key-row">
            <input type="password" id="rawgKeyInput" class="arte-key-input" placeholder="••••••••••••••••••••"
              autocomplete="new-password" onblur="saveApiKey('rawg_api_key', this.value)">
            <button class="btn-eye" type="button" title="Mostrar key" onclick="toggleKeyVisibility(this)">👁</button>
            <div class="info-wrap" onclick="toggleInfo(this)">
              <button class="info-btn" type="button">?</button>
              <div class="info-popup">
                <strong>Cómo obtener la key:</strong>
                <ol style="margin-top:6px">
                  <li>Ve a <strong>rawg.io</strong></li>
                  <li>Regístrate con email o Steam</li>
                  <li>Perfil → <strong>API key</strong></li>
                  <li>Se genera automáticamente</li>
                  <li>Copia y pega la key aquí</li>
                </ol>
              </div>
            </div>
          </div>
          <a href="https://rawg.io/apidocs" target="_blank" class="arte-key-link" style="margin-top:6px;display:inline-block">rawg.io ↗</a>
        </div>
      </details>

      <details class="settings-section">
        <summary>
          <span style="display:flex;align-items:center;gap:8px">
            <span class="section-title">Icono local del exe</span>
            <span class="arte-source-badge free">Sin API key</span>
          </span>
          <span class="section-arrow">▶</span>
        </summary>
        <div class="section-body">
          <div style="font-family:var(--mono);font-size:11px;color:var(--muted)">
            Extrae el icono incrustado en el ejecutable. Funciona para cualquier app Windows.
            <span style="display:block;margin-top:2px">🎯 Todas las apps &nbsp;·&nbsp; 🖼 Icono</span>
          </div>
        </div>
      </details>

      <div style="font-size:10px;color:var(--muted);font-family:var(--mono);padding:8px 0">
        Orden: Steam CDN → SteamGridDB → RAWG → Icono local
      </div>
    </div>

    <!-- Tab: Profiles -->
    <div class="settings-body" id="tabProfiles" style="display:none">
      <div>
        <div class="setting-group-label">Profiles</div>
        <div id="profilesList"></div>
        <button class="btn-ghost" style="margin-top:4px;width:100%;font-size:12px" onclick="newProfile()">+ New profile</button>
      </div>
      <div>
        <div class="setting-group-label">Migrate profile</div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <select id="migrateFrom" class="mini-select"></select>
          <span style="color:var(--muted);font-family:var(--mono);font-size:11px;flex-shrink:0">→</span>
          <select id="migrateTo" class="mini-select"></select>
          <button class="btn-primary" style="font-size:11px;padding:6px 14px;flex-shrink:0" onclick="confirmMigrate()">Migrate</button>
        </div>
        <p style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:6px">Moves all apps and sessions from source to destination (source becomes empty)</p>
      </div>
      <div>
        <div class="setting-group-label">Export profile</div>
        <div style="display:flex;gap:8px;align-items:center">
          <select id="exportProfile" class="mini-select"></select>
          <button class="btn-ghost" style="font-size:11px;padding:6px 14px;flex-shrink:0" onclick="doExportProfile()">↓ Download JSON</button>
        </div>
      </div>
      <div>
        <div class="setting-group-label">Import profile</div>
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <label style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border:1px solid var(--border);
                 border-radius:7px;font-family:var(--sans);font-size:11px;color:var(--muted);cursor:pointer;
                 transition:all .15s" onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--accent)'"
                 onmouseout="this.style.borderColor='';this.style.color=''">
            ↑ Import JSON
            <input type="file" accept=".json" onchange="importProfileFile(this)" style="display:none">
          </label>
          <span style="font-family:var(--mono);font-size:10px;color:var(--muted)" id="importStatus"></span>
        </div>
        <p style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:6px">Genera un perfil nuevo con los datos del JSON — no reemplaza el perfil activo.</p>
      </div>
    </div>

    <div class="modal-foot">
      <button class="btn-ghost" onclick="closeSettings()">Cerrar</button>
    </div>
  </div>
</div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  document.body.insertAdjacentHTML('beforeend', _buildSettingsModal());
});
