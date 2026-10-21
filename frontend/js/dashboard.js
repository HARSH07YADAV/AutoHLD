/**
 * dashboard.js — Executive Dashboard metrics and visual analytics.
 */

window.DashboardModule = (() => {
  async function refresh() {
    try {
      const data = await API.listDocuments();
      const docs = Array.isArray(data) ? data : (data.documents || []);



      // Update Active Document Spotlight
      updateSpotlight(docs);

      // If active doc exists, fetch detailed dashboard metrics
      if (App.currentDocId) {
        await refreshDocDashboard(App.currentDocId);
      } else {
        renderUnselectedState();
      }

      // Also refresh HomeModule document list
      if (window.HomeModule?.renderDocList) {
        window.HomeModule.renderDocList(docs);
      }
    } catch (err) {
      console.warn('Dashboard refresh error:', err);
    }
  }

  function updateSpotlight(docs) {
    const filenameEl = document.getElementById('spotlight-filename');
    const metaEl = document.getElementById('spotlight-meta');

    if (!App.currentDocId) {
      if (filenameEl) filenameEl.textContent = 'No specification selected';
      if (metaEl) metaEl.textContent = 'Select an uploaded PDF or upload a new HLD document below';
      return;
    }

    const currentDoc = docs.find(d => d.doc_id === App.currentDocId);
    const fname = currentDoc?.filename || App.currentDocName || 'Specification';

    if (filenameEl) filenameEl.textContent = fname;
    if (metaEl) {
      const pages = currentDoc?.page_count || App.currentDocMeta?.page_count || '?';
      const chunks = currentDoc?.chunk_count || App.currentDocMeta?.chunk_count || '?';
      const status = currentDoc?.status || App.currentDocMeta?.status || 'ready';
      metaEl.textContent = `${pages} pages · ${chunks} semantic vector chunks · Status: ${status.toUpperCase()}`;
    }
  }

  async function refreshDocDashboard(docId) {
    try {
      const dashData = await API.getDashboardData(docId);
      const counts = dashData.entity_counts || {};
      const incs = dashData.inconsistency_summary || {};



      // Update Visual Analytics: Entity breakdown bar
      updateEntityBar(counts);

      // Update Visual Analytics: Severity meters
      updateSeverityMeters(incs);

      // Update sidebar badge
      const navBadge = document.getElementById('nav-badge-consistency');
      if (navBadge) {
        const total = incs.total ?? 0;
        if (total > 0) {
          navBadge.textContent = total;
          navBadge.classList.remove('hidden');
        } else {
          navBadge.classList.add('hidden');
        }
      }
    } catch (err) {
      console.warn('Document dashboard data fetch error:', err);
    }
  }

  function updateEntityBar(c) {
    const total = (c.components || 0) + (c.interfaces || 0) + (c.ports || 0) + (c.signals || 0);

    const swcCount = c.components || 0;
    const ifaceCount = c.interfaces || 0;
    const portCount = c.ports || 0;
    const signalCount = c.signals || 0;

    const legSwc = document.getElementById('legend-swc');
    const legIface = document.getElementById('legend-iface');
    const legPort = document.getElementById('legend-port');
    const legSignal = document.getElementById('legend-signal');

    if (legSwc) legSwc.textContent = `SWCs: ${swcCount}`;
    if (legIface) legIface.textContent = `Interfaces: ${ifaceCount}`;
    if (legPort) legPort.textContent = `Ports: ${portCount}`;
    if (legSignal) legSignal.textContent = `Signals: ${signalCount}`;

    const bar = document.getElementById('analytics-entity-bar');
    if (!bar) return;

    if (total === 0) {
      bar.innerHTML = `<div class="bar-segment" style="width: 100%; background: var(--bg-surface-2);" title="Pending Extraction"></div>`;
      return;
    }

    const swcPct = Math.round((swcCount / total) * 100);
    const ifacePct = Math.round((ifaceCount / total) * 100);
    const portPct = Math.round((portCount / total) * 100);
    const sigPct = Math.max(0, 100 - swcPct - ifacePct - portPct);

    bar.innerHTML = `
      <div class="bar-segment bar-segment--swc" style="width: ${swcPct}%;" title="Software Components (${swcCount})"></div>
      <div class="bar-segment bar-segment--iface" style="width: ${ifacePct}%;" title="Interfaces (${ifaceCount})"></div>
      <div class="bar-segment bar-segment--port" style="width: ${portPct}%;" title="Ports (${portCount})"></div>
      <div class="bar-segment bar-segment--signal" style="width: ${sigPct}%;" title="Signals (${signalCount})"></div>
    `;
  }

  function updateSeverityMeters(s) {
    const cntW = document.getElementById('dash-cnt-warning');
    const cntR = document.getElementById('dash-cnt-review');
    const cntI = document.getElementById('dash-cnt-info');

    const fillW = document.getElementById('meter-fill-warning');
    const fillR = document.getElementById('meter-fill-review');
    const fillI = document.getElementById('meter-fill-info');

    const w = s.warning ?? 0;
    const r = s.review ?? 0;
    const i = s.info ?? 0;
    const max = Math.max(10, w + r + i);

    if (cntW) cntW.textContent = w;
    if (cntR) cntR.textContent = r;
    if (cntI) cntI.textContent = i;

    if (fillW) fillW.style.width = `${Math.min(100, Math.round((w / max) * 100))}%`;
    if (fillR) fillR.style.width = `${Math.min(100, Math.round((r / max) * 100))}%`;
    if (fillI) fillI.style.width = `${Math.min(100, Math.round((i / max) * 100))}%`;
  }

  function renderUnselectedState() {
    updateEntityBar({ components: 0, interfaces: 0, ports: 0, signals: 0 });
    updateSeverityMeters({ warning: 0, review: 0, info: 0 });
  }

  return { refresh };
})();
