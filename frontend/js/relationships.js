/**
 * relationships.js — Logic for Section 6: Dependencies & Architecture Graph.
 */

window.RelationshipsModule = (() => {
  const diagramEl    = document.getElementById('rel-flow-diagram');
  const tableBody    = document.getElementById('rel-table-body');
  const swcFilterEl  = document.getElementById('rel-swc-filter');
  const refreshBtn   = document.getElementById('rel-refresh-btn');

  let currentGraphData = null;

  function init() {
    refreshBtn?.addEventListener('click', async () => {
      if (!App.currentDocId) {
        showToast('Please select a document first.', 'error');
        return;
      }
      try {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<span class="spinner"></span> Refreshing…';
        await refresh();
        showToast('Connections refreshed', 'info');
      } finally {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh`;
      }
    });

    swcFilterEl?.addEventListener('change', () => {
      renderCurrentGraph();
    });
  }

  async function refresh() {
    const docId = App.currentDocId;
    if (!docId) {
      renderEmpty();
      return;
    }

    try {
      const data = await API.getRelationships(docId);
      currentGraphData = data;
      populateFilter(data.nodes || []);
      renderCurrentGraph();
    } catch (err) {
      console.warn('Relationships fetch error:', err);
      renderError(err.message);
    }
  }

  function populateFilter(nodes) {
    if (!swcFilterEl) return;
    const comps = nodes.filter(n => n.type === 'component');
    const prev = swcFilterEl.value;

    swcFilterEl.innerHTML = '<option value="all">Show All Components</option>';
    comps.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.id;
      swcFilterEl.appendChild(opt);
    });

    if (comps.some(c => c.id === prev)) {
      swcFilterEl.value = prev;
    }
  }

  function renderCurrentGraph() {
    if (!currentGraphData || !diagramEl) return;

    const nodes = currentGraphData.nodes || [];
    const edges = currentGraphData.edges || [];
    const ports = currentGraphData.ports || [];
    const selectedSWC = swcFilterEl ? swcFilterEl.value : 'all';

    // Filter components
    let comps = nodes.filter(n => n.type === 'component');
    if (selectedSWC !== 'all') {
      comps = comps.filter(c => c.id === selectedSWC);
    }

    if (comps.length === 0) {
      diagramEl.innerHTML = `
        <div class="table-empty">No software components found. Run "Identify Components" on the Architecture Overview page first.</div>
      `;
    } else {
      const rowsHtml = comps.map(comp => {
        // Find ports matching component page or context
        const compPorts = ports.filter(p => p.page === comp.page);

        const portItems = compPorts.length > 0 
          ? compPorts.map(p => {
              const dir = p.subtype?.includes('P-Port') || (p.name || '').includes('_Prov') ? 'P-Port' : 'R-Port';
              const arrow = dir === 'P-Port' ? '➔' : '🠔';
              const pillClass = dir === 'P-Port' ? 'p-port' : 'r-port';
              const iface = p.details?.associated_interface || '';

              return `
                <div class="port-item">
                  <span style="color:var(--text-muted); font-size:10px;">${arrow}</span>
                  <span class="port-pill ${pillClass}">${dir}</span>
                  <span style="font-weight:600; color:var(--text-primary);">${escapeHtml(p.name)}</span>
                  ${iface ? `<span class="iface-pill">${escapeHtml(iface)}</span>` : ''}
                </div>
              `;
            }).join('')
          : '<span style="color:var(--text-muted); font-size:11px;">No ports detected on this component page</span>';

        return `
          <div class="swc-flow-row">
            <div class="swc-box">
              <div class="swc-title">${escapeHtml(comp.id)}</div>
              <div class="swc-sub">Software Component (SWC) · Page ${comp.page || '—'}</div>
            </div>
            <div class="port-flow-list">
              ${portItems}
            </div>
          </div>
        `;
      }).join('');

      diagramEl.innerHTML = rowsHtml;
    }

    // Render Table
    if (tableBody) {
      let filteredEdges = edges;
      if (selectedSWC !== 'all') {
        filteredEdges = edges.filter(e => e.source === selectedSWC || e.target === selectedSWC);
      }

      if (filteredEdges.length === 0) {
        tableBody.innerHTML = `
          <tr><td colspan="5" class="table-empty">No connections found for the selected component.</td></tr>
        `;
        return;
      }

      tableBody.innerHTML = filteredEdges.map(e => `
        <tr>
          <td style="font-weight: 600; font-family: var(--font-mono); font-size: 13px; color: var(--accent);">${escapeHtml(e.source)}</td>
          <td><span class="badge badge-info">${escapeHtml(e.relation)}</span></td>
          <td style="font-family: var(--font-mono); font-size: 13px; font-weight: 600;">${escapeHtml(e.target)}</td>
          <td><span class="badge-page">Page ${e.page || '—'}</span></td>
          <td><span class="badge badge-${(e.confidence || 'medium').toLowerCase()}">${e.confidence || 'Medium'}</span></td>
        </tr>
      `).join('');
    }
  }

  function renderEmpty() {
    if (diagramEl) diagramEl.innerHTML = '<div class="table-empty">Select a document to see component connections.</div>';
    if (tableBody) tableBody.innerHTML = '<tr><td colspan="5" class="table-empty">No connections found.</td></tr>';
  }

  function renderError(msg) {
    if (diagramEl) diagramEl.innerHTML = `<div class="table-empty" style="color:var(--danger)">Could not load connections: ${escapeHtml(msg)}</div>`;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  init();

  return { refresh };
})();
