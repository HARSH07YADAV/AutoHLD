/**
 * analysis.js — Logic for "Engineering Review & Inconsistency Audit" page.
 * Distinguishes AI-generated observations from engineer-verified findings
 * with actionable remediation steps and disposition workflows.
 */

window.InconsistencyModule = (() => {
  const containerEl   = document.getElementById('findings-container');
  const runBtn        = document.getElementById('consistency-run-btn');
  const filterPills   = document.getElementById('consistency-filter-pills');
  const searchInput   = document.getElementById('findings-search');
  const cntTotal      = document.getElementById('cnt-total');
  const cntWarning    = document.getElementById('cnt-warning');
  const cntReview     = document.getElementById('cnt-review');
  const cntInfo       = document.getElementById('cnt-info');

  let allFindings = [];
  let currentFilter = 'all';
  let dispositions = {}; // finding index -> status

  function init() {
    runBtn?.addEventListener('click', async () => {
      const docId = App.currentDocId;
      if (!docId) {
        showToast('Please select a specification document first.', 'error');
        return;
      }

      runBtn.disabled = true;
      runBtn.innerHTML = '<span class="spinner"></span> Running Consistency Audit…';

      try {
        const data = await API.runConsistencyCheck(docId);
        showToast('Consistency audit complete', 'success');
        renderFindingsData(data);
        if (window.DashboardModule?.refresh) await window.DashboardModule.refresh();
      } catch (err) {
        showToast(`Audit failed: ${err.message}`, 'error', 4000);
      } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Run Consistency Audit
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

    searchInput?.addEventListener('input', () => {
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
              No audit findings stored for this specification.<br>
              Click <strong>Run Consistency Audit</strong> to inspect the document against AUTOSAR design rules.
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
  }

  /**
   * Synthesize engineering remediation recommendation based on finding category
   */
  function getRemediationAdvice(finding) {
    const cat = (finding.category || '').toLowerCase();
    const desc = (finding.description || '').toLowerCase();

    if (desc.includes('p-port') && desc.includes('r-port') || cat.includes('port')) {
      return 'Check AUTOSAR port prototype direction: verify whether the requiring component should specify an R-Port instead of a P-Port to maintain contract pairing with the provider.';
    }
    if (cat.includes('interface') || desc.includes('interface')) {
      return 'Review interface definition contract in ARXML/specification: confirm sender-receiver data elements, data types, and transmission periodicity.';
    }
    if (cat.includes('missing') || desc.includes('missing')) {
      return 'Document completeness issue: ensure mandatory architectural sections, ASIL safety goals, and execution timing parameters are properly documented.';
    }
    if (cat.includes('signal') || desc.includes('signal')) {
      return 'Signal mapping verification: check signal routing between application layer SWCs and RTE / IO Hardware Abstraction.';
    }
    return 'Inspect the originating specification page and consult the lead systems architect before updating the baseline design.';
  }

  function renderCards() {
    if (!containerEl) return;

    const query = (searchInput?.value || '').toLowerCase().trim();

    let filtered = allFindings.filter(f => {
      if (currentFilter !== 'all' && f.severity !== currentFilter) {
        return false;
      }
      if (query) {
        const titleMatch = (f.title || '').toLowerCase().includes(query);
        const descMatch = (f.description || '').toLowerCase().includes(query);
        const catMatch = (f.category || '').toLowerCase().includes(query);
        const pageMatch = (f.pages || []).some(p => String(p).includes(query));
        if (!titleMatch && !descMatch && !catMatch && !pageMatch) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      containerEl.innerHTML = `
        <div class="table-empty" style="padding: 40px 20px;">
          No findings match the selected filter criteria.
        </div>
      `;
      return;
    }

    const severityLabel = { warning: 'Warning / High', review: 'Needs Review / Medium', info: 'Informational / Low' };
    const cardClass     = { warning: 'finding-card--warning', review: 'finding-card--review', info: 'finding-card--info' };
    const badgeClass    = { warning: 'badge-danger', review: 'badge-review', info: 'badge-info' };

    containerEl.innerHTML = filtered.map((f, idx) => {
      const sev = (f.severity || 'info').toLowerCase();
      const pagesStr = (f.pages || []).map(p => `Page ${p}`).join(', ') || 'General';
      const cardId = `finding-card-${idx}`;
      const dispStatus = dispositions[idx] || 'Unverified';

      let dispBadgeHtml = '<span class="badge badge-unverified">AI-Observed (Unverified)</span>';
      if (dispStatus === 'Verified') {
        dispBadgeHtml = '<span class="badge badge-verified">✓ Engineer Verified</span>';
      } else if (dispStatus === 'Dismissed') {
        dispBadgeHtml = '<span class="badge badge-dismissed">✕ Dismissed (False Positive)</span>';
      } else if (dispStatus === 'Reviewed') {
        dispBadgeHtml = '<span class="badge badge-accent">Reviewed &amp; Noted</span>';
      }

      const remediation = getRemediationAdvice(f);

      return `
        <div class="finding-card ${cardClass[sev] || ''} ${dispStatus === 'Dismissed' ? 'finding-dismissed' : ''}" id="${cardId}">
          <div class="finding-card-header" onclick="InconsistencyModule.toggleCard('${cardId}')" role="button" tabindex="0" aria-expanded="false">
            <span class="badge ${badgeClass[sev] || 'badge-info'}">${severityLabel[sev] || sev}</span>
            ${dispBadgeHtml}
            <div class="finding-card-title">${escapeHtml(f.title || f.description)}</div>
            <span class="finding-card-pages">${pagesStr}</span>
            <span class="finding-toggle-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </div>

          <div class="finding-card-body">
            <p class="finding-description">${escapeHtml(f.description)}</p>

            <div style="margin-bottom: 12px;">
              <div class="finding-detail-label">Document Evidence (Excerpt from ${pagesStr}):</div>
              <div class="finding-evidence">${escapeHtml(f.evidence || '(No direct text quote captured for this check)')}</div>
            </div>

            <div style="margin-bottom: 12px;">
              <div class="finding-detail-label">Automated Detection Rationale:</div>
              <p class="finding-reason">${escapeHtml(f.reason || 'Flagged by heuristic architectural rule matching.')}</p>
            </div>

            <div style="margin-bottom: 16px;">
              <div class="finding-detail-label">Recommended Engineering Next Steps:</div>
              <div class="finding-action-steps">${escapeHtml(remediation)}</div>
            </div>

            <div class="finding-actions">
              <span class="finding-category-label">Category: <strong>${escapeHtml(f.category || 'general')}</strong></span>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button class="btn btn-sm btn-secondary" onclick="InconsistencyModule.setDisposition(${idx}, '${cardId}', 'Verified')">
                  Verify Issue
                </button>
                <button class="btn btn-sm btn-ghost" onclick="InconsistencyModule.setDisposition(${idx}, '${cardId}', 'Reviewed')">
                  Mark Reviewed
                </button>
                <button class="btn btn-sm btn-ghost" onclick="InconsistencyModule.setDisposition(${idx}, '${cardId}', 'Dismissed')">
                  Dismiss False Positive
                </button>
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

  function setDisposition(idx, cardId, status) {
    dispositions[idx] = status;
    renderCards();
    showToast(`Finding marked as: ${status}`, 'info');
  }

  function renderEmpty() {
    if (containerEl) {
      containerEl.innerHTML = `<div class="table-empty" style="padding: 40px 20px;">Select a document specification to run consistency review.</div>`;
    }
    updateCounters({ total: 0, warning: 0, review: 0, info: 0 });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  init();

  return {
    refresh,
    toggleCard,
    setDisposition,
  };
})();
