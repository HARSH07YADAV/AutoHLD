/**
 * overview.js — Logic for the Architecture Overview page.
 */

window.OverviewModule = (() => {
  const swcCountEl     = document.getElementById('overview-swc-count');
  const ifaceCountEl   = document.getElementById('overview-iface-count');
  const portCountEl    = document.getElementById('overview-port-count');
  const signalCountEl  = document.getElementById('overview-signal-count');
  const distributionEl = document.getElementById('overview-distribution-body');
  const extractBtn     = document.getElementById('overview-extract-btn');

  function init() {
    extractBtn?.addEventListener('click', async () => {
      if (!App.currentDocId) {
        showToast('Please select a document first.', 'error');
        return;
      }
      try {
        extractBtn.disabled = true;
        extractBtn.innerHTML = '<span class="spinner"></span> Identifying…';
        await API.extractEntities(App.currentDocId);
        showToast('Components identified successfully.', 'success');
        await refresh();
      } catch (err) {
        showToast(`Could not identify components: ${err.message}`, 'error');
      } finally {
        extractBtn.disabled = false;
        extractBtn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Identify Components
        `;
      }
    });
  }

  async function refresh() {
    const docId = App.currentDocId;
    if (!docId) {
      renderEmpty();
      return;
    }

    try {
      const reportRes = await API.getReport(docId);
      const data = reportRes.report_data;

      const counts = data.entity_counts || {};
      if (swcCountEl)    swcCountEl.textContent    = counts.components ?? 0;
      if (ifaceCountEl)  ifaceCountEl.textContent  = counts.interfaces ?? 0;
      if (portCountEl)   portCountEl.textContent   = counts.ports ?? 0;
      if (signalCountEl) signalCountEl.textContent = counts.signals ?? 0;

      renderPageDistribution(data);
    } catch (err) {
      console.warn('Architecture overview fetch error:', err);
      renderEmpty();
    }
  }

  function renderPageDistribution(data) {
    if (!distributionEl) return;
    const pageTrace = data.page_traceability || {};
    const pageCount = data.document_metadata?.page_count || Object.keys(pageTrace).length;

    if (pageCount === 0) {
      distributionEl.innerHTML = `
        <tr><td colspan="4" class="table-empty">No page data available. Run "Identify Components" first.</td></tr>
      `;
      return;
    }

    const rows = [];
    for (let p = 1; p <= pageCount; p++) {
      const pData = pageTrace[p] || { entities: [], findings: [], inconsistencies: [] };
      const ents  = pData.entities || [];

      const normalizedEnts = ents.map(e => {
        if (typeof e === 'string') {
          return {
            name: e.replace(' (component)', '').trim(),
            isComponent: e.includes('(component)')
          };
        } else if (e && typeof e === 'object') {
          return {
            name: e.name || e.id || '',
            isComponent: (e.type === 'component' || e.entity_type === 'component')
          };
        }
        return { name: String(e || ''), isComponent: false };
      });

      const swcs = normalizedEnts.filter(e => e.isComponent).map(e => e.name).filter(Boolean);
      const portsAndIfaces = normalizedEnts.filter(e => !e.isComponent).map(e => e.name).filter(Boolean);

      let scope = 'General content';
      if (swcs.length > 0 && portsAndIfaces.length > 0) {
        scope = 'Components & interfaces';
      } else if (swcs.length > 0) {
        scope = 'Software components';
      } else if (portsAndIfaces.length > 0) {
        scope = 'Interfaces & signals';
      }

      const findingsCount = (pData.findings?.length || pData.inconsistencies?.length || 0);

      rows.push(`
        <tr>
          <td style="font-weight: 600; color: var(--accent); font-family: var(--font-mono);">Page ${p}</td>
          <td>
            ${swcs.length > 0
              ? swcs.map(s => `<span class="badge badge-accent" style="margin-right: 4px; margin-bottom: 4px;">${escapeHtml(s)}</span>`).join('')
              : '<span style="color: var(--text-muted); font-size: 12px;">—</span>'}
          </td>
          <td>
            ${portsAndIfaces.length > 0
              ? portsAndIfaces.slice(0, 4).map(i => `<span style="font-size: 12px; color: var(--text-secondary); margin-right: 8px; font-family: var(--font-mono);">${escapeHtml(i)}</span>`).join('')
                + (portsAndIfaces.length > 4 ? `<span style="color: var(--text-muted); font-size: 11px;">+${portsAndIfaces.length - 4} more</span>` : '')
              : '<span style="color: var(--text-muted); font-size: 12px;">—</span>'}
          </td>
          <td>
            <span class="badge badge-info">${scope}</span>
            ${findingsCount > 0 ? `<span class="badge badge-warning" style="margin-left: 6px;">${findingsCount} findings</span>` : ''}
          </td>
        </tr>
      `);
    }

    distributionEl.innerHTML = rows.join('');
  }

  function renderEmpty() {
    if (swcCountEl)    swcCountEl.textContent    = '—';
    if (ifaceCountEl)  ifaceCountEl.textContent  = '—';
    if (portCountEl)   portCountEl.textContent   = '—';
    if (signalCountEl) signalCountEl.textContent = '—';
    if (distributionEl) {
      distributionEl.innerHTML = `
        <tr><td colspan="4" class="table-empty">Select a document and click "Identify Components" to see architecture details.</td></tr>
      `;
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  init();

  return { refresh };
})();
