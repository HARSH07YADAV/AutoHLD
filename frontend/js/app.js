/**
 * app.js — Global State, Sidebar Navigation, Theme Toggle, Document Selector & Status.
 */

const App = {
  currentDocId: null,
  currentDocName: null,
  currentDocMeta: null,
};

// ── Sidebar Navigation ────────────────────────────────────────────────────────
function switchTab(tabName) {
  // Update nav items
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });

  // Update pages
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const activePanel = document.getElementById(`panel-${tabName}`);
  if (activePanel) activePanel.classList.add('active');

  // Update URL hash without jumping
  if (window.location.hash !== `#${tabName}`) {
    history.replaceState(null, '', `#${tabName}`);
  }

  // Close sidebar on mobile after navigation
  closeMobileSidebar();

  // Trigger tab-specific refresh if document is loaded
  if (App.currentDocId) {
    if (tabName === 'home' && window.HomeModule?.refresh) {
      window.HomeModule.refresh();
    } else if (tabName === 'overview' && window.OverviewModule?.refresh) {
      window.OverviewModule.refresh();
    } else if (tabName === 'components' && window.ComponentsModule?.refresh) {
      window.ComponentsModule.refresh();
    } else if (tabName === 'relationships' && window.RelationshipsModule?.refresh) {
      window.RelationshipsModule.refresh();
    } else if (tabName === 'consistency' && window.InconsistencyModule?.refresh) {
      window.InconsistencyModule.refresh();
    } else if (tabName === 'reports' && window.ReportsModule?.refresh) {
      window.ReportsModule.refresh();
    } else if (tabName === 'qa' && window.QueryModule?.refresh) {
      window.QueryModule.refresh();
    }
  }
}

// Wire up all nav items
document.querySelectorAll('.nav-item[data-tab]').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ── Mobile Sidebar Toggle ─────────────────────────────────────────────────────
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const sidebarToggle = document.getElementById('sidebar-toggle');

function openMobileSidebar() {
  sidebar?.classList.add('sidebar-open');
  sidebarOverlay?.classList.remove('hidden');
}

function closeMobileSidebar() {
  sidebar?.classList.remove('sidebar-open');
  sidebarOverlay?.classList.add('hidden');
}

sidebarToggle?.addEventListener('click', openMobileSidebar);
sidebarOverlay?.addEventListener('click', closeMobileSidebar);

// ── Toast Notifications ───────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 3200) {
  const toast = document.getElementById('toast-notification');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast ${type}`;

  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => {
    toast.classList.add('hidden');
  }, duration);
}

// ── Theme Toggling ────────────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('autohld_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);

  const btn = document.getElementById('theme-toggle');
  if (btn) {
    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('autohld_theme', next);
    });
  }
}

// ── Document Selector ─────────────────────────────────────────────────────────
// Support both mobile header selector and settings page selector
const docSelectors = [
  document.getElementById('doc-selector'),
  document.getElementById('doc-selector-settings'),
];

async function refreshDocSelector(autoSelectFirst = true) {
  try {
    const data = await API.listDocuments();
    const docs = Array.isArray(data) ? data : (data.documents || []);

    docSelectors.forEach(sel => {
      if (!sel) return;
      sel.innerHTML = '<option value="">— No document selected —</option>';
      docs.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.doc_id;
        opt.textContent = d.filename;
        if (d.status !== 'ready') opt.textContent += ` [${d.status}]`;
        sel.appendChild(opt);
      });
      if (App.currentDocId) sel.value = App.currentDocId;
    });

    if (!App.currentDocId && autoSelectFirst && docs.length > 0) {
      const readyDoc = docs.find(d => d.status === 'ready') || docs[0];
      selectDocument(readyDoc.doc_id, readyDoc.filename, readyDoc);
      docSelectors.forEach(sel => { if (sel) sel.value = readyDoc.doc_id; });
    }

    // Refresh home doc list
    if (window.HomeModule?.renderDocList) {
      window.HomeModule.renderDocList(docs);
    }

    return docs;
  } catch (err) {
    console.warn('Failed to load document list:', err);
    return [];
  }
}

function selectDocument(docId, filename, meta = null) {
  if (!docId) {
    App.currentDocId = null;
    App.currentDocName = null;
    App.currentDocMeta = null;
    updateSidebarDocIndicator(null, null);
    return;
  }

  App.currentDocId = docId;
  App.currentDocName = filename || docId;
  App.currentDocMeta = meta;

  docSelectors.forEach(sel => { if (sel) sel.value = docId; });
  updateSidebarDocIndicator(filename, meta);

  // Update QA no-doc notice
  const qaNotice = document.getElementById('qa-no-doc-notice');
  if (qaNotice) qaNotice.style.display = 'none';

  // Refresh active page
  const hash = (window.location.hash || '').replace('#', '');
  const activePage = document.querySelector('.page.active');
  const targetTab = (hash && ['home', 'upload', 'qa', 'overview', 'components', 'relationships', 'consistency', 'reports', 'settings'].includes(hash))
    ? hash
    : (activePage ? activePage.id.replace('panel-', '') : 'home');
  switchTab(targetTab);
}

function updateSidebarDocIndicator(filename, meta) {
  const nameEl = document.getElementById('sidebar-doc-name');
  const statusEl = document.getElementById('sidebar-doc-status');

  if (!filename) {
    if (nameEl) nameEl.textContent = 'No document selected';
    if (statusEl) statusEl.textContent = '';
    return;
  }

  if (nameEl) {
    nameEl.textContent = filename.length > 28 ? filename.slice(0, 25) + '…' : filename;
  }
  if (statusEl) {
    if (meta?.status === 'ready') {
      statusEl.textContent = `${meta.page_count || '?'} pages · Ready`;
      statusEl.style.color = 'var(--success)';
    } else {
      statusEl.textContent = meta?.status || '';
      statusEl.style.color = 'var(--text-muted)';
    }
  }
}

// Wire doc selectors
docSelectors.forEach(sel => {
  if (!sel) return;
  sel.addEventListener('change', async () => {
    const docId = sel.value;
    if (!docId) { selectDocument(null, null); return; }

    try {
      const docs = await API.listDocuments();
      const docList = Array.isArray(docs) ? docs : (docs.documents || []);
      const meta = docList.find(d => d.doc_id === docId) || null;
      selectDocument(docId, meta?.filename || docId, meta);
      showToast(`Document selected: ${meta?.filename || docId}`, 'info');
    } catch (_) {
      selectDocument(docId, docId, null);
    }
  });
});

// ── LLM Status ────────────────────────────────────────────────────────────────
async function checkLLMStatus() {
  const dots = [
    document.getElementById('status-dot'),
    document.getElementById('settings-status-dot'),
  ];
  const labels = [
    document.getElementById('llm-model-label'),
    document.getElementById('settings-llm-label'),
  ];

  try {
    const data = await API.getLLMStatus();
    const online = data.available;
    const text = data.available ? 'Active & Connected' : 'Engine offline';

    dots.forEach(d => { if (d) { d.className = `status-dot ${online ? 'online' : 'offline'}`; } });
    labels.forEach(l => { 
      if (l) {
        l.textContent = text;
        l.title = data.available ? `${data.provider}/${data.model}` : 'Engine offline';
      }
    });
  } catch (_) {
    dots.forEach(d => { if (d) d.className = 'status-dot offline'; });
    labels.forEach(l => { if (l) l.textContent = 'Engine offline'; });
  }
}

// ── Home Module ───────────────────────────────────────────────────────────────
window.HomeModule = (() => {
  async function refresh() {
    try {
      const data = await API.listDocuments();
      const docs = Array.isArray(data) ? data : (data.documents || []);
      renderDocList(docs);
    } catch (err) {
      console.warn('Failed to load home doc list:', err);
    }
  }

  function renderDocList(docs) {
    const container = document.getElementById('home-doc-list');
    if (!container) return;

    if (!docs || docs.length === 0) {
      container.innerHTML = `
        <div class="home-empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          </div>
          <h3>No documents yet</h3>
          <p>Upload a PDF to begin your analysis.</p>
          <button class="btn btn-primary" onclick="switchTab('upload')">Upload a Document</button>
        </div>
      `;
      return;
    }

    container.innerHTML = docs.map(d => {
      const isActive = d.doc_id === App.currentDocId;
      const statusLabel = d.status === 'ready' ? `${d.page_count || '?'} pages` : d.status;
      const uploadDate = d.upload_time ? new Date(d.upload_time).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '';

      return `
        <div class="home-doc-card ${isActive ? 'active-doc' : ''}" onclick="HomeModule.selectDoc('${d.doc_id}')">
          <div class="home-doc-card-body">
            <div class="home-doc-card-name" title="${escapeHtml(d.filename)}">${escapeHtml(d.filename)}</div>
            <div class="home-doc-card-meta">${statusLabel}${uploadDate ? ' · ' + uploadDate : ''}</div>
            <div class="home-doc-card-actions" onclick="event.stopPropagation()">
              ${isActive ? `
                <span class="doc-badge-active">Active</span>
                <button class="btn btn-sm btn-ghost" onclick="HomeModule.selectDoc('${d.doc_id}'); switchTab('qa');">Ask Question</button>
              ` : `
                <button class="btn btn-sm btn-ghost" onclick="HomeModule.selectDoc('${d.doc_id}')">Select</button>
                <button class="btn btn-sm btn-ghost" onclick="HomeModule.selectDoc('${d.doc_id}'); switchTab('qa');">Ask Question</button>
              `}
            </div>
          </div>
          <div class="home-doc-thumbnail" aria-hidden="true">
            <div class="doc-thumb-paper">
              <div class="doc-thumb-header-bar"></div>
              <div class="doc-thumb-line" style="width: 80%;"></div>
              <div class="doc-thumb-line" style="width: 90%;"></div>
              <div class="doc-thumb-line" style="width: 70%;"></div>
              <div class="doc-thumb-box"></div>
              <div class="doc-thumb-line" style="width: 85%;"></div>
              <div class="doc-thumb-line" style="width: 60%;"></div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  async function selectDoc(docId, filename) {
    try {
      const docs = await API.listDocuments();
      const docList = Array.isArray(docs) ? docs : (docs.documents || []);
      const meta = docList.find(d => d.doc_id === docId) || null;
      const docName = filename || meta?.filename || 'Document';
      selectDocument(docId, docName, meta);
      renderDocList(docList);
      showToast(`Selected: ${docName}`, 'info');
    } catch (err) {
      selectDocument(docId, filename || 'Document', null);
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;');
  }
  window.escapeHtml = escapeHtml;

  return { refresh, renderDocList, selectDoc };
})();

// ── Dashboard Module Stub (for compatibility) ─────────────────────────────────
// The old dashboard.js still references KPI elements — provide a fallback
window.DashboardModule = {
  refresh: async function() {
    await window.HomeModule?.refresh();
  }
};

// ── Application Bootstrap ─────────────────────────────────────────────────────
(async function init() {
  initTheme();

  try {
    await checkLLMStatus();
    await refreshDocSelector(true);
  } catch (err) {
    console.warn('Init error:', err);
  }

  const hash = (window.location.hash || '').replace('#', '');
  if (hash && ['home', 'upload', 'qa', 'overview', 'components', 'relationships', 'consistency', 'reports', 'settings'].includes(hash)) {
    switchTab(hash);
  }
  window.addEventListener('hashchange', () => {
    const nextTab = (window.location.hash || '').replace('#', '');
    if (nextTab && ['home', 'upload', 'qa', 'overview', 'components', 'relationships', 'consistency', 'reports', 'settings'].includes(nextTab)) {
      switchTab(nextTab);
    }
  });
  setInterval(checkLLMStatus, 60000);
})();

