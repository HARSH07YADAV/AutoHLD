/**
 * components.js — Logic for Section 5: Components & Interfaces Catalog.
 */

window.ComponentsModule = (() => {
  const tableBody     = document.getElementById('entities-table-body');
  const searchInput   = document.getElementById('entity-search');
  const extractBtn    = document.getElementById('entities-extract-btn');
  const exportCsvBtn  = document.getElementById('entities-export-csv-btn');
  const exportJsonBtn = document.getElementById('entities-export-json-btn');
  const filterPills   = document.getElementById('entity-filter-pills');

  let allEntities = [];
  let currentFilter = 'all';

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
        extractBtn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> Identify Components`;
      }
    });

    searchInput?.addEventListener('input', () => renderFiltered());

    filterPills?.addEventListener('click', (e) => {
      const btn = e.target.closest('.filter-pill');
      if (!btn) return;
      filterPills.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter || 'all';
      renderFiltered();
    });

    exportCsvBtn?.addEventListener('click', () => exportCSV());
    exportJsonBtn?.addEventListener('click', () => exportJSON());
  }

  async function refresh() {
    const docId = App.currentDocId;
    if (!docId) {
      allEntities = [];
      renderFiltered();
      return;
    }

    try {
      const data = await API.getReport(docId);
      const repData = data.report_data || {};

      // Flatten entities with entity_type
      const comps = (repData.components || []).map(e => ({ ...e, entity_type: 'component' }));
      const ifaces = (repData.interfaces || []).map(e => ({ ...e, entity_type: 'interface' }));
      const ports = (repData.ports || []).map(e => ({ ...e, entity_type: 'port' }));
      const signals = (repData.signals || []).map(e => ({ ...e, entity_type: 'signal' }));

      allEntities = [...comps, ...ifaces, ...ports, ...signals];
      renderFiltered();
    } catch (err) {
      console.warn('Components fetch error:', err);
      tableBody.innerHTML = `
        <tr><td colspan="5" class="table-empty" style="color:var(--danger)">Could not load components: ${err.message}</td></tr>
      `;
    }
  }

  function renderFiltered() {
    if (!tableBody) return;

    if (!App.currentDocId) {
      tableBody.innerHTML = `
        <tr><td colspan="5" class="table-empty">Select a document to see its components and interfaces.</td></tr>
      `;
      return;
    }

    const query = (searchInput?.value || '').toLowerCase().trim();

    let filtered = allEntities.filter(e => {
      if (currentFilter !== 'all' && e.entity_type !== currentFilter) {
        return false;
      }
      if (query) {
        const nameMatch = (e.name || '').toLowerCase().includes(query);
        const typeMatch = (e.entity_type || '').toLowerCase().includes(query);
        const subMatch = (e.details?.subtype || '').toLowerCase().includes(query);
        const pageMatch = String(e.page_ref || '').includes(query);
        if (!nameMatch && !typeMatch && !subMatch && !pageMatch) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      tableBody.innerHTML = `
        <tr><td colspan="5" class="table-empty">No components match your search. Click "Identify Components" if you have not run analysis yet.</td></tr>
      `;
      return;
    }

    tableBody.innerHTML = filtered.map(e => {
      const details = e.details || {};
      const subtype = details.subtype || '—';
      const conf = details.confidence || 'medium';
      const confBadge = `<span class="badge badge-${conf.toLowerCase()}">${conf.charAt(0).toUpperCase() + conf.slice(1)}</span>`;
      const typeBadge = `<span class="badge badge-info">${(e.entity_type || '').charAt(0).toUpperCase() + (e.entity_type || '').slice(1)}</span>`;

      return `
        <tr>
          <td style="font-weight: 600; font-family: var(--font-mono); font-size: 13px;">${escapeHtml(e.name)}</td>
          <td>${typeBadge}</td>
          <td style="color: var(--text-secondary); font-size: 13px;">${escapeHtml(subtype)}</td>
          <td><span class="badge-page">Page ${e.page_ref || '—'}</span></td>
          <td>${confBadge}</td>
        </tr>
      `;
    }).join('');
  }

  function exportCSV() {
    if (allEntities.length === 0) {
      showToast('No entities to export', 'error');
      return;
    }

    const headers = ['Name', 'Entity Type', 'Subtype', 'Page', 'Confidence', 'Context'];
    const rows = allEntities.map(e => [
      `"${(e.name || '').replace(/"/g, '""')}"`,
      `"${e.entity_type}"`,
      `"${(e.details?.subtype || '').replace(/"/g, '""')}"`,
      `"${e.page_ref || ''}"`,
      `"${e.details?.confidence || 'medium'}"`,
      `"${(e.details?.source_text || '').replace(/"/g, '""')}"`,
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `${App.currentDocName || 'AUTOSAR'}_Entities.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast('Exported CSV', 'info');
  }

  function exportJSON() {
    if (allEntities.length === 0) {
      showToast('No entities to export', 'error');
      return;
    }

    const jsonStr = JSON.stringify(allEntities, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${App.currentDocName || 'AUTOSAR'}_Entities.json`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('Exported JSON', 'info');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  init();

  return { refresh };
})();
