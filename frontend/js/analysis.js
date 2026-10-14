/**
 * analysis.js — Logic for "Review Findings" page (Inconsistency checks).
 */

window.InconsistencyModule = (() => {
  const containerEl   = document.getElementById('findings-container');
  const runBtn        = document.getElementById('consistency-run-btn');
  const filterPills   = document.getElementById('consistency-filter-pills');
  const cntTotal      = document.getElementById('cnt-total');
  const cntWarning    = document.getElementById('cnt-warning');
  const cntReview     = document.getElementById('cnt-review');
  const cntInfo       = document.getElementById('cnt-info');

  let allFindings = [];
  let currentFilter = 'all';

  function init() {
    runBtn?.addEventListener('click', async () => {
      const docId = App.currentDocId;
      if (!docId) {
        showToast('Please select a document first.', 'error');
        return;
      }

      runBtn.disabled = true;
      runBtn.innerHTML = '<span class="spinner"></span> Checking…';

      try {
        const data = await API.runConsistencyCheck(docId);
        showToast('Check complete', 'success');
        renderFindingsData(data);
      } catch (err) {
        showToast(`Check failed: ${err.message}`, 'error', 4000);
      } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Run Check
        `;
      }
    });

    filterPills?.addEventListener('click', (e) => {
      const btn = e.target.closest('.filter-pill');
      if (!btn) return;
      filterPills.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.sev || 'all';
      renderCards();
    });
  }

  async function refresh() {
    const docId = App.currentDocId;
    if (!docId) {
      renderEmpty();
      return;
    }

    try {
      const data = await API.getInconsistencyReport(docId);
      if (data.checked && data.findings?.length > 0) {
        renderFindingsData(data);
      } else {
        if (containerEl) {
          containerEl.innerHTML = `
            <div class="table-empty" style="padding: 40px 20px;">
              No findings stored yet.<br>Click <strong>Run Check</strong> to look for possible issues in the document.
            </div>
          `;
        }
        updateCounters({ total: 0, warning: 0, review: 0, info: 0 });
      }
    } catch (err) {
      console.warn('Findings fetch error:', err);
    }
  }

  function renderFindingsData(data) {
    allFindings = data.findings || [];

    const summary = data.summary || {
      total:   allFindings.length,
      warning: allFindings.filter(f => f.severity === 'warning').length,
      review:  allFindings.filter(f => f.severity === 'review').length,
      info:    allFindings.filter(f => f.severity === 'info').length,
    };

    updateCounters(summary);
    renderCards();
  }

  function updateCounters(s) {
    if (cntTotal)   cntTotal.textContent   = s.total   ?? 0;
    if (cntWarning) cntWarning.textContent = s.warning ?? 0;
    if (cntReview)  cntReview.textContent  = s.review  ?? 0;
    if (cntInfo)    cntInfo.textContent    = s.info    ?? 0;

    // Update sidebar nav badge
    const navBadge = document.getElementById('nav-badge-consistency');
    if (navBadge) {
      if ((s.total ?? 0) > 0) {
        navBadge.textContent = s.total;
        navBadge.classList.remove('hidden');
      } else {
        navBadge.classList.add('hidden');
      }
    }

    // Legacy tab badge compatibility
    const tabBadge = document.getElementById('tab-badge-consistency');
    if (tabBadge) {
      if ((s.total ?? 0) > 0) {
        tabBadge.textContent = s.total;
        tabBadge.classList.remove('hidden');
      } else {
        tabBadge.classList.add('hidden');
      }
    }
  }

  function renderCards() {
    if (!containerEl) return;

    let filtered = allFindings;
    if (currentFilter !== 'all') {
      filtered = allFindings.filter(f => f.severity === currentFilter);
    }

    if (filtered.length === 0) {
      containerEl.innerHTML = `
        <div class="table-empty" style="padding: 40px 20px;">
          No findings match the selected filter.
        </div>
      `;
      return;
    }

    // Map severity to user-friendly labels and card classes
    const severityLabel = { warning: 'Warning', review: 'Needs Review', info: 'Informational' };
    const cardClass     = { warning: 'finding-card--warning', review: 'finding-card--review', info: 'finding-card--info' };
    const badgeClass    = { warning: 'badge-danger', review: 'badge-review', info: 'badge-info' };

    containerEl.innerHTML = filtered.map((f, idx) => {
      const sev = (f.severity || 'info').toLowerCase();
      const pagesStr = (f.pages || []).map(p => `p.${p}`).join(', ') || '—';
      const cardId = `finding-card-${idx}`;

      return `
        <div class="finding-card ${cardClass[sev] || ''}" id="${cardId}">
          <div class="finding-card-header" onclick="InconsistencyModule.toggleCard('${cardId}')" role="button" tabindex="0" aria-expanded="false">
            <span class="badge ${badgeClass[sev] || 'badge-info'}">${severityLabel[sev] || sev}</span>
            <div class="finding-card-title">${escapeHtml(f.title || f.description)}</div>
            <span class="finding-card-pages">Pages: ${pagesStr}</span>
            <span class="finding-toggle-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>

          <div class="finding-card-body">
            <p class="finding-description">${escapeHtml(f.description)}</p>

            <div style="margin-bottom: 14px;">
              <div class="finding-detail-label">Evidence from the document:</div>
              <div class="finding-evidence">${escapeHtml(f.evidence || '(No excerpt captured for this finding)')}</div>
            </div>

            <div style="margin-bottom: 14px;">
              <div class="finding-detail-label">Why this was flagged:</div>
              <p class="finding-reason">${escapeHtml(f.reason || 'Flagged by an automated pattern check.')}</p>
            </div>

            <div class="finding-actions">
              <span class="finding-category-label">Category: ${escapeHtml(f.category || 'general')}</span>
              <div style="display: flex; gap: 8px;">
                <button class="btn btn-sm btn-ghost" onclick="InconsistencyModule.setDisposition('${cardId}', 'Reviewed')">Mark Reviewed</button>
                <button class="btn btn-sm btn-ghost" onclick="InconsistencyModule.setDisposition('${cardId}', 'Dismissed')">Dismiss</button>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  function toggleCard(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const isOpen = el.classList.toggle('open');
    const header = el.querySelector('.finding-card-header');
    if (header) header.setAttribute('aria-expanded', isOpen);
  }

  function setDisposition(id, status) {
    const el = document.getElementById(id);
    if (!el) return;
    showToast(`Finding marked as: ${status}`, 'info');
    el.style.opacity = '0.55';
  }

  function renderEmpty() {
    if (containerEl) {
      containerEl.innerHTML = `<div class="table-empty" style="padding: 40px 20px;">Select a document to check for possible issues.</div>`;
    }
    updateCounters({ total: 0, warning: 0, review: 0, info: 0 });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  init();

  return {
    refresh,
    toggleCard,
    setDisposition,
  };
})();
