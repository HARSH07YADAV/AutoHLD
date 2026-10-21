/**
 * relationships.js — Interactive Architecture Graph with Search, Port Filters,
 * Zoom Controls, and Component Inspector Drawer.
 */

window.RelationshipsModule = (() => {
  const diagramEl       = document.getElementById('rel-flow-diagram');
  const viewportEl      = document.getElementById('rel-diagram-viewport');
  const tableBody       = document.getElementById('rel-table-body');
  const swcFilterEl     = document.getElementById('rel-swc-filter');
  const portTypeFilterEl= document.getElementById('rel-port-type-filter');
  const searchInputEl   = document.getElementById('rel-search-input');
  const refreshBtn      = document.getElementById('rel-refresh-btn');
  const connCountBadge  = document.getElementById('rel-connection-count');

  // Zoom buttons
  const zoomInBtn       = document.getElementById('rel-zoom-in');
  const zoomOutBtn      = document.getElementById('rel-zoom-out');
  const zoomResetBtn    = document.getElementById('rel-zoom-reset');

  // Inspector Drawer
  const inspectorDrawer = document.getElementById('component-details-drawer');
  const inspectorName   = document.getElementById('inspector-comp-name');
  const inspectorBody   = document.getElementById('inspector-body');
  const inspectorClose  = document.getElementById('inspector-close-btn');

  let currentGraphData  = null;
  let zoomLevel         = 1.0;
  let activeSelectedComp= null;

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
        showToast('Architecture graph refreshed', 'info');
      } finally {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh Graph`;
      }
    });

    swcFilterEl?.addEventListener('change', () => renderCurrentGraph());
    portTypeFilterEl?.addEventListener('change', () => renderCurrentGraph());
    searchInputEl?.addEventListener('input', () => renderCurrentGraph());

    // Zoom handlers
    zoomInBtn?.addEventListener('click', () => {
      zoomLevel = Math.min(1.8, zoomLevel + 0.15);
      applyZoom();
    });
    zoomOutBtn?.addEventListener('click', () => {
      zoomLevel = Math.max(0.6, zoomLevel - 0.15);
      applyZoom();
    });
    zoomResetBtn?.addEventListener('click', () => {
      zoomLevel = 1.0;
      applyZoom();
    });

    // Inspector close handler
    inspectorClose?.addEventListener('click', () => {
      if (inspectorDrawer) inspectorDrawer.classList.add('hidden');
      activeSelectedComp = null;
      document.querySelectorAll('.swc-card-interactive').forEach(c => c.classList.remove('active-node'));
    });
  }

  function applyZoom() {
    if (diagramEl) {
      diagramEl.style.transformOrigin = 'top left';
      diagramEl.style.transform = `scale(${zoomLevel})`;
      diagramEl.style.transition = 'transform 0.15s ease-out';
    }
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

    swcFilterEl.innerHTML = '<option value="all">All Software Components</option>';
    comps.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.id} (Page ${c.page || '—'})`;
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
    const selectedPortType = portTypeFilterEl ? portTypeFilterEl.value : 'all';
    const searchQuery = (searchInputEl?.value || '').toLowerCase().trim();

    // Filter components
    let comps = nodes.filter(n => n.type === 'component');
    if (selectedSWC !== 'all') {
      comps = comps.filter(c => c.id === selectedSWC);
    }
    if (searchQuery) {
      comps = comps.filter(c => {
        const nameMatch = c.id.toLowerCase().includes(searchQuery);
        const compPorts = ports.filter(p => p.page === c.page);
        const portMatch = compPorts.some(p => (p.name || '').toLowerCase().includes(searchQuery) || (p.details?.associated_interface || '').toLowerCase().includes(searchQuery));
        return nameMatch || portMatch;
      });
    }

    if (comps.length === 0) {
      diagramEl.innerHTML = `
        <div class="table-empty" style="padding: 40px 20px;">
          No software components match your filter criteria.<br>
          Click <strong>Identify Components</strong> on the Component Catalog page if analysis has not been run.
        </div>
      `;
    } else {
      const cardsHtml = comps.map(comp => {
        // Find ports matching this component's page or context
        let compPorts = ports.filter(p => p.page === comp.page);

        // Apply port type filter
        if (selectedPortType === 'p-port') {
          compPorts = compPorts.filter(p => p.subtype?.includes('P-Port') || (p.name || '').includes('_Prov'));
        } else if (selectedPortType === 'r-port') {
          compPorts = compPorts.filter(p => p.subtype?.includes('R-Port') || (p.name || '').includes('_Req'));
        }

        const pPorts = compPorts.filter(p => p.subtype?.includes('P-Port') || (p.name || '').includes('_Prov'));
        const rPorts = compPorts.filter(p => p.subtype?.includes('R-Port') || (p.name || '').includes('_Req'));

        const pPortItems = pPorts.map(p => {
          const iface = p.details?.associated_interface || '';
          return `
            <div class="port-item" title="Provided Port: ${escapeHtml(p.name)}">
              <span class="p-port-badge">➔ P-Port</span>
              <span style="font-weight:600; color:var(--text-primary);">${escapeHtml(p.name)}</span>
              ${iface ? `<span class="interface-chip">${escapeHtml(iface)}</span>` : ''}
            </div>
          `;
        }).join('');

        const rPortItems = rPorts.map(p => {
          const iface = p.details?.associated_interface || '';
          return `
            <div class="port-item" title="Required Port: ${escapeHtml(p.name)}">
              <span class="r-port-badge">🠔 R-Port</span>
              <span style="font-weight:600; color:var(--text-primary);">${escapeHtml(p.name)}</span>
              ${iface ? `<span class="interface-chip">${escapeHtml(iface)}</span>` : ''}
            </div>
          `;
        }).join('');

        const isCurrentActive = activeSelectedComp === comp.id;

        return `
          <div class="swc-card-interactive ${isCurrentActive ? 'active-node' : ''}"
               onclick="RelationshipsModule.inspectComponent('${escapeHtml(comp.id)}')">
            <div class="swc-header-interactive">
              <div>
                <span class="swc-name-badge">${escapeHtml(comp.id)}</span>
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                  AUTOSAR SWC · <span class="badge-page">Page ${comp.page || '—'}</span>
                </div>
              </div>
              <span class="badge badge-${(comp.confidence || 'medium').toLowerCase()}">${comp.confidence || 'High'}</span>
            </div>

            <div style="margin-bottom: 8px;">
              <div style="font-size: 10.5px; font-weight: 700; text-transform: uppercase; color: #60a5fa; margin-bottom: 4px;">
                Provided Interfaces &amp; Ports (${pPorts.length})
              </div>
              <div class="port-flow-list">
                ${pPortItems || '<span style="color:var(--text-muted); font-size:11px;">No P-Ports defined</span>'}
              </div>
            </div>

            <div style="margin-top: 10px; border-top: 1px solid var(--border-subtle); padding-top: 8px;">
              <div style="font-size: 10.5px; font-weight: 700; text-transform: uppercase; color: #c084fc; margin-bottom: 4px;">
                Required Interfaces &amp; Ports (${rPorts.length})
              </div>
              <div class="port-flow-list">
                ${rPortItems || '<span style="color:var(--text-muted); font-size:11px;">No R-Ports defined</span>'}
              </div>
            </div>
          </div>
        `;
      }).join('');

      diagramEl.innerHTML = `<div class="arch-node-grid">${cardsHtml}</div>`;
    }

    // Render Table
    if (tableBody) {
      let filteredEdges = edges;
      if (selectedSWC !== 'all') {
        filteredEdges = edges.filter(e => e.source === selectedSWC || e.target === selectedSWC);
      }
      if (searchQuery) {
        filteredEdges = filteredEdges.filter(e =>
          (e.source || '').toLowerCase().includes(searchQuery) ||
          (e.target || '').toLowerCase().includes(searchQuery) ||
          (e.relation || '').toLowerCase().includes(searchQuery)
        );
      }

      if (connCountBadge) {
        connCountBadge.textContent = `${filteredEdges.length} interface bindings`;
      }

      if (filteredEdges.length === 0) {
        tableBody.innerHTML = `
          <tr><td colspan="5" class="table-empty">No connections found for the selected component or search term.</td></tr>
        `;
        return;
      }

      tableBody.innerHTML = filteredEdges.map(e => `
        <tr>
          <td style="font-weight: 600; font-family: var(--font-mono); font-size: 13px; color: var(--accent);">${escapeHtml(e.source)}</td>
          <td><span class="badge badge-info">${escapeHtml(e.relation)}</span></td>
          <td style="font-family: var(--font-mono); font-size: 13px; font-weight: 600; color: #a78bfa;">${escapeHtml(e.target)}</td>
          <td><span class="badge-page">Page ${e.page || '—'}</span></td>
          <td><span class="badge badge-${(e.confidence || 'medium').toLowerCase()}">${e.confidence || 'Medium'}</span></td>
        </tr>
      `).join('');
    }
  }

  function inspectComponent(compId) {
    activeSelectedComp = compId;
    renderCurrentGraph();

    if (!inspectorDrawer || !inspectorBody) return;
    inspectorDrawer.classList.remove('hidden');
    if (inspectorName) inspectorName.textContent = compId;

    const nodes = currentGraphData?.nodes || [];
    const ports = currentGraphData?.ports || [];
    const edges = currentGraphData?.edges || [];

    const compNode = nodes.find(n => n.id === compId && n.type === 'component');
    const compPorts = ports.filter(p => p.page === compNode?.page);
    const relatedEdges = edges.filter(e => e.source === compId || e.target === compId);

    inspectorBody.innerHTML = `
      <div style="margin-bottom: 14px;">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px;">Classification</div>
        <div style="font-size: 13px; color: var(--text-primary); font-weight: 600;">AUTOSAR Application Software Component</div>
        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Document Location: Page ${compNode?.page || '—'}</div>
      </div>

      <div style="margin-bottom: 14px;">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px;">Port Inventory (${compPorts.length})</div>
        <div style="display:flex; flex-direction:column; gap:6px;">
          ${compPorts.map(p => `
            <div style="background:var(--bg-surface); border:1px solid var(--border); padding:6px 10px; border-radius:4px; font-size:12px; font-family:var(--font-mono);">
              <span class="${p.subtype?.includes('P-Port') ? 'p-port-badge' : 'r-port-badge'}">${p.subtype || 'Port'}</span>
              <span style="font-weight:600; color:var(--text-primary);">${escapeHtml(p.name)}</span>
              ${p.details?.associated_interface ? `<div style="font-size:11px; color:var(--text-muted); margin-top:2px;">↳ ${escapeHtml(p.details.associated_interface)}</div>` : ''}
            </div>
          `).join('') || '<span style="font-size:12px; color:var(--text-muted);">No ports linked on page</span>'}
        </div>
      </div>

      <div style="margin-bottom: 14px;">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px;">Connected Interface Bindings (${relatedEdges.length})</div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          ${relatedEdges.map(e => `
            <div style="font-size:12px; font-family:var(--font-mono); color:var(--text-secondary);">
              ➔ ${escapeHtml(e.relation)}: <strong style="color:var(--text-primary);">${escapeHtml(e.target)}</strong>
            </div>
          `).join('') || '<span style="font-size:12px; color:var(--text-muted);">No bindings detected</span>'}
        </div>
      </div>

      <div style="margin-top: 18px; display:flex; gap:8px;">
        <button class="btn btn-primary btn-sm" style="width:100%;" onclick="QueryModule.submitQuestionFromComponent('${escapeHtml(compId)}')">
          Query Component Q&amp;A
        </button>
      </div>
    `;
  }

  function renderEmpty() {
    if (diagramEl) diagramEl.innerHTML = '<div class="table-empty" style="padding: 40px 20px;">Select a specification document to explore component connections.</div>';
    if (tableBody) tableBody.innerHTML = '<tr><td colspan="5" class="table-empty">No connections found.</td></tr>';
    if (connCountBadge) connCountBadge.textContent = '0 bindings';
    if (inspectorDrawer) inspectorDrawer.classList.add('hidden');
  }

  function renderError(msg) {
    if (diagramEl) diagramEl.innerHTML = `<div class="table-empty" style="color:var(--danger)">Could not load architecture graph: ${escapeHtml(msg)}</div>`;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  init();

  return { refresh, inspectComponent };
})();
