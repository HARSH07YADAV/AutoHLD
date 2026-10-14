/**
 * reports.js — Engineering Report Generation & Preview
 *
 * Renders the full 13-section engineering analysis report in the browser.
 * Each section clearly labels its source type:
 *   [EXTRACTED]   — direct text from the PDF source
 *   [INFERRED]    — AI/pattern analysis
 *   [RULE-BASED]  — deterministic consistency rules
 *   [AI-GENERATED] — LLM answers
 */

window.ReportsModule = (() => {
  /* ── DOM handles ────────────────────────────────────────────────────────── */
  const toolbar     = document.getElementById('report-toolbar');
  const preview     = document.getElementById('report-preview');
  const generateBtn = document.getElementById('report-generate-btn');
  const downloadBtn = document.getElementById('report-download-btn');
  const copyBtn     = document.getElementById('report-copy-btn');
  const qaToggle    = document.getElementById('report-qa-toggle');

  let currentMarkdown  = '';
  let currentReportData = null;

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* ── Init ────────────────────────────────────────────────────────────────── */
  function init() {
    generateBtn?.addEventListener('click', async () => {
      if (!App.currentDocId) {
        showToast('Select a document first.', 'error');
        return;
      }
      setGenerating(true);
      try {
        await refresh();
        showToast('Report generated.', 'success');
      } catch (err) {
        showToast(`Report error: ${err.message}`, 'error');
      } finally {
        setGenerating(false);
      }
    });

    copyBtn?.addEventListener('click', async () => {
      if (!currentMarkdown) { showToast('Nothing to copy.', 'error'); return; }
      try {
        await navigator.clipboard.writeText(currentMarkdown);
        showToast('Markdown copied to clipboard.', 'info');
      } catch (_) {
        showToast('Clipboard access not available.', 'error');
      }
    });
  }

  /* ── Refresh ────────────────────────────────────────────────────────────── */
  async function refresh() {
    const docId = App.currentDocId;
    if (!docId) { renderEmpty(); return; }

    const includeQa = qaToggle ? qaToggle.checked : true;
    const url       = `/api/reports/${encodeURIComponent(docId)}?include_qa=${includeQa}`;

    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      currentMarkdown   = data.markdown   || '';
      currentReportData = data.report_data || null;

      renderReport(currentReportData, currentMarkdown);

      if (downloadBtn) {
        const pdfUrl  = `/api/reports/${encodeURIComponent(docId)}/download?include_qa=${includeQa}`;
        const mdUrl   = `/api/reports/${encodeURIComponent(docId)}/download/markdown?include_qa=${includeQa}`;
        const fname   = (currentReportData?.filename || 'AutoHLD').replace('.pdf', '').replace(/\s+/g, '_');

        downloadBtn.href = pdfUrl;
        downloadBtn.setAttribute('download', `${fname}_AutoHLD_Engineering_Report.pdf`);
        downloadBtn.title = 'Download full report as PDF';
        downloadBtn.textContent = '⬇ Download PDF';

        // Attach / update the markdown download link
        let mdBtn = document.getElementById('report-download-md-btn');
        if (!mdBtn) {
          mdBtn = document.createElement('a');
          mdBtn.id        = 'report-download-md-btn';
          mdBtn.className = downloadBtn.className + ' btn-ghost';
          mdBtn.style.fontSize = '12px';
          downloadBtn.parentElement.insertBefore(mdBtn, downloadBtn.nextSibling);
        }
        mdBtn.href     = mdUrl;
        mdBtn.setAttribute('download', `${fname}_AutoHLD_Engineering_Report.md`);
        mdBtn.title    = 'Download as Markdown';
        mdBtn.textContent = '.md';
      }
    } catch (err) {
      console.error('Reports fetch:', err);
      renderError(err.message);
    }
  }

  /* ── Full report renderer ─────────────────────────────────────────────────
   * We render using structured data (not raw Markdown) so we can control
   * layout and highlight source-type badges exactly.
   * ───────────────────────────────────────────────────────────────────────── */
  function renderReport(rd, rawMd) {
    if (!preview) return;

    if (!rd) {
      preview.innerHTML = `<pre class="report-raw-md">${escapeHtml(rawMd)}</pre>`;
      return;
    }

    const dm     = rd.document_metadata || {};
    const ps     = rd.processing_summary || {};
    const rs     = rd.review_status || {};
    const inc_sum = rd.inconsistency_summary || {};

    preview.innerHTML = `
      <!-- NOTICE BANNER -->
      ${renderNoticeBanner(rd.disclaimer_short)}

      <!-- COVER -->
      ${renderSection('Cover & Document Identification', '', renderCover(rd, dm, rs))}

      <!-- SECTION 1: METHODOLOGY -->
      ${renderSection('Engineering Notice & Methodology', '', renderMethodology(rd.disclaimer_full))}

      <!-- SECTION 2: DOC INFO -->
      ${renderSection('Document Information', '', renderDocInfo(rd, dm))}

      <!-- SECTION 3: PROCESSING -->
      ${renderSection('Processing & Extraction Summary', '', renderProcessingSummary(ps, rd))}

      <!-- SECTION 4: COMPONENTS -->
      ${renderSection('Software Components (SWCs) Identified',
          badge('INFERRED', 'inferred'),
          renderComponents(rd.components || []))}

      <!-- SECTION 5: INTERFACES -->
      ${renderSection('Interfaces Identified',
          badge('INFERRED', 'inferred'),
          renderInterfaces(rd.interfaces || []))}

      <!-- SECTION 6: PORTS -->
      ${renderSection('Ports (P-Port / R-Port) Catalogue',
          badge('INFERRED', 'inferred'),
          renderPorts(rd.ports || []))}

      <!-- SECTION 7: SIGNALS -->
      ${renderSection('Signals Identified',
          badge('INFERRED', 'inferred'),
          renderSignals(rd.signals || []))}

      <!-- SECTION 8: DEPENDENCIES -->
      ${renderSection('Component Dependencies & Connectivity',
          badge('INFERRED', 'inferred'),
          renderDependencies(rd.dependency_links || []))}

      <!-- SECTION 9: ARCH FINDINGS -->
      ${renderSection('Architecture Findings from Grounded Q&A',
          badge('AI-GENERATED', 'ai'),
          renderArchFindings(rd.architecture_findings || []))}

      <!-- SECTION 10: INCONSISTENCIES -->
      ${renderSection('Architecture Inconsistency Findings',
          badge('RULE-BASED', 'rule'),
          renderInconsistencies(rd.inconsistencies || [], inc_sum))}

      <!-- SECTION 11: QA LOG -->
      ${rd.include_qa
        ? renderSection('Q&A Session Log & Source References',
            badge('AI-GENERATED + EXTRACTED', 'mixed'),
            renderQaLog(rd.query_log || []))
        : ''}

      <!-- SECTION 12: TRACEABILITY -->
      ${renderSection('Source Evidence & Page Traceability Index',
          badge('EXTRACTED', 'extracted'),
          renderTraceability(rd.page_traceability || {}))}

      <!-- SECTION 13: SIGN-OFF -->
      ${renderSection('Review Status & Engineering Sign-off', '', renderSignoff(ps, dm, rs))}
    `;
  }

  /* ── Section helpers ─────────────────────────────────────────────────────── */

  function renderSection(title, badgeHtml, content) {
    return `
      <section class="report-section">
        <div class="report-section-header">
          <h2 class="report-section-title">${escapeHtml(title)}</h2>
          ${badgeHtml}
        </div>
        <div class="report-section-body">${content}</div>
      </section>`;
  }

  function badge(label, type) {
    return `<span class="source-badge source-badge--${type}">${label}</span>`;
  }

  function renderNoticeBanner(text) {
    return `
      <div class="report-notice-banner">
        <span class="report-notice-icon">⚠</span>
        <span>${escapeHtml(text || '')}</span>
      </div>`;
  }

  /* Cover */
  function renderCover(rd, dm, rs) {
    const statusCls = { warning: 'danger', review: 'warning', info: 'info', success: 'success', pending: 'muted' }[rs.color] || 'muted';
    return `
      <div class="report-cover-grid">
        ${coverField('Document File', `<code>${escapeHtml(rd.filename)}</code>`)}
        ${coverField('Document ID', `<code>${escapeHtml(rd.doc_id)}</code>`)}
        ${coverField('Report Generated', escapeHtml(rd.generated_at))}
        ${coverField('Analysis Tool', escapeHtml(rd.tool_version))}
        ${coverField('Ingestion Status', `<span class="status-dot status-dot--${dm.status === 'ready' ? 'success' : 'warning'}"></span> ${escapeHtml(dm.status?.toUpperCase() || '—')}`)}
        ${coverField('Pages Analyzed', String(dm.page_count ?? '—'))}
        ${coverField('Semantic Chunks Indexed', String(dm.chunk_count ?? '—'))}
        ${coverField('Ingestion Timestamp', escapeHtml(dm.upload_time || '—'))}
      </div>
      <div class="report-review-status report-review-status--${statusCls}">
        <strong>Overall Review Status:</strong> ${escapeHtml(rs.overall || '—')}
      </div>`;
  }

  function coverField(label, valueHtml) {
    return `<div class="cover-field"><div class="cover-field-label">${escapeHtml(label)}</div><div class="cover-field-value">${valueHtml}</div></div>`;
  }

  /* Methodology */
  function renderMethodology(text) {
    if (!text) return '<p class="report-muted">Methodology not available.</p>';
    return `<pre class="report-methodology-text">${escapeHtml(text)}</pre>`;
  }

  /* Doc Info */
  function renderDocInfo(rd, dm) {
    return dataTable([
      ['Filename', `<code>${escapeHtml(rd.filename)}</code>`],
      ['Total Pages Processed', String(dm.page_count ?? '—')],
      ['Vector Chunk Count', String(dm.chunk_count ?? '—')],
      ['Vector Embedding Model', 'all-MiniLM-L6-v2 (384-dim, Cosine similarity)'],
      ['LLM Reasoning Engine', 'Ollama — qwen2.5:1.5b (local inference, no cloud)'],
      ['Vector Store', 'ChromaDB (local persistent collection)'],
      ['Entity Extraction Method', 'Regex + AUTOSAR naming-convention heuristics'],
      ['Consistency Rule Engine', '5 deterministic document-level rules'],
    ]);
  }

  /* Processing Summary */
  function renderProcessingSummary(ps, rd) {
    const eb = ps.entities_by_type || {};
    const cd = ps.confidence_distribution || {};

    const stageRows = [
      ['PDF Ingestion', rd.document_metadata?.status === 'ready' ? '✓ Complete' : '⚠ ' + (rd.document_metadata?.status || '?'), String(rd.document_metadata?.page_count ?? '—') + ' pages'],
      ['Vector Indexing', rd.document_metadata?.chunk_count > 0 ? '✓ Complete' : '—', String(rd.document_metadata?.chunk_count ?? '—') + ' chunks'],
      ['Entity Extraction', ps.extraction_performed ? '✓ Performed' : '⚠ Pending', String(ps.total_entities_found ?? 0) + ' entities'],
      ['Consistency Check', ps.consistency_checked ? '✓ Performed' : '⚠ Pending', String(rd.inconsistency_count ?? 0) + ' findings'],
      ['Q&A Sessions', ps.qa_sessions > 0 ? '✓ Recorded' : '— None', String(ps.qa_sessions ?? 0) + ' queries'],
    ];

    const entityRows = ['components', 'interfaces', 'ports', 'signals'].map(type => {
      const n = eb[type] || 0;
      const conf = cd[type] || {};
      const h = conf.high || 0;
      const m = conf.medium || 0;
      const l = (conf.low || 0) + (conf.uncertain || 0);
      return [type.charAt(0).toUpperCase() + type.slice(1), String(n), String(h), String(m), String(l)];
    });

    return `
      <h4 class="report-subheading">Analysis Stage Summary</h4>
      <table class="report-table">
        <thead><tr><th>Stage</th><th>Status</th><th>Metric</th></tr></thead>
        <tbody>${stageRows.map(r => `<tr>${r.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody>
      </table>
      <h4 class="report-subheading" style="margin-top:1.2rem">Entity Extraction Breakdown</h4>
      <table class="report-table">
        <thead><tr><th>Entity Type</th><th>Count</th><th>High Confidence</th><th>Medium</th><th>Low / Uncertain</th></tr></thead>
        <tbody>${entityRows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? '' : ' style="text-align:center"'}>${escapeHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody>
      </table>
      <p class="report-muted" style="margin-top:.6rem">
        Confidence levels reflect pattern-match strength only.
        All entities with confidence &lt; high must be manually verified against the source arxml or document text.
      </p>`;
  }

  /* Components */
  function renderComponents(items) {
    if (!items.length) return `<p class="report-muted">No software components identified. Run entity extraction in the Components &amp; Interfaces tab.</p>`;
    return `
      <p class="report-entity-count">${items.length} software component(s) identified.</p>
      <table class="report-table">
        <thead><tr><th>#</th><th>Component Name</th><th>Subtype</th><th>Source Page</th><th>Confidence</th><th>Evidence Excerpt ${badge('EXTRACTED', 'extracted')}</th></tr></thead>
        <tbody>
          ${items.map((c, i) => {
            const det = c.details || {};
            return `<tr>
              <td>${i + 1}</td>
              <td><code>${escapeHtml(c.name)}</code></td>
              <td>${escapeHtml(det.subtype || 'SWC')}</td>
              <td>p.${c.page_ref || '—'}</td>
              <td>${confBadge(det.confidence || 'medium')}</td>
              <td class="report-excerpt">${escapeHtml(trunc(det.source_text || '—', 120))}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  /* Interfaces */
  function renderInterfaces(items) {
    if (!items.length) return `<p class="report-muted">No interfaces identified.</p>`;
    return `
      <p class="report-entity-count">${items.length} interface(s) identified.</p>
      <table class="report-table">
        <thead><tr><th>#</th><th>Interface Name</th><th>Type</th><th>Source Page</th><th>Confidence</th><th>Evidence ${badge('EXTRACTED', 'extracted')}</th></tr></thead>
        <tbody>
          ${items.map((iface, i) => {
            const det = iface.details || {};
            return `<tr>
              <td>${i + 1}</td>
              <td><code>${escapeHtml(iface.name)}</code></td>
              <td>${escapeHtml(det.subtype || 'SenderReceiver')}</td>
              <td>p.${iface.page_ref || '—'}</td>
              <td>${confBadge(det.confidence || 'medium')}</td>
              <td class="report-excerpt">${escapeHtml(trunc(det.source_text || '—', 120))}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  /* Ports */
  function renderPorts(items) {
    if (!items.length) return `<p class="report-muted">No ports identified.</p>`;
    return `
      <p class="report-entity-count">${items.length} port(s) identified.</p>
      <table class="report-table">
        <thead><tr><th>#</th><th>Port Name</th><th>Direction</th><th>Associated Interface</th><th>Source Page</th><th>Confidence</th></tr></thead>
        <tbody>
          ${items.map((p, i) => {
            const det = p.details || {};
            const iface = det.associated_interface || '—';
            return `<tr>
              <td>${i + 1}</td>
              <td><code>${escapeHtml(p.name)}</code></td>
              <td>${escapeHtml(det.subtype || 'Port')}</td>
              <td><code>${escapeHtml(iface)}</code></td>
              <td>p.${p.page_ref || '—'}</td>
              <td>${confBadge(det.confidence || 'medium')}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  /* Signals */
  function renderSignals(items) {
    if (!items.length) return `<p class="report-muted">No signals identified.</p>`;
    return `
      <p class="report-entity-count">${items.length} signal(s) identified.</p>
      <table class="report-table">
        <thead><tr><th>#</th><th>Signal Name</th><th>Type</th><th>Source Page</th><th>Confidence</th></tr></thead>
        <tbody>
          ${items.map((sig, i) => {
            const det = sig.details || {};
            return `<tr>
              <td>${i + 1}</td>
              <td><code>${escapeHtml(sig.name)}</code></td>
              <td>${escapeHtml(det.subtype || 'Signal')}</td>
              <td>p.${sig.page_ref || '—'}</td>
              <td>${confBadge(det.confidence || 'medium')}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  /* Dependencies */
  function renderDependencies(links) {
    if (!links.length) {
      return `
        <p class="report-muted">No port-level dependencies inferred from naming conventions.</p>
        <ul class="report-muted-list">
          <li>Ports may use non-standard naming conventions</li>
          <li>Extraction may not yet have been run</li>
          <li>The document may describe a single SWC boundary</li>
        </ul>
        <p class="report-muted">Dependencies in this report are inferred by matching P-Port and R-Port base names (e.g., BattSOC_Prov ↔ BattSOC_Req). Actual connectivity requires arxml / RTE configuration verification.</p>`;
    }
    return `
      <p class="report-entity-count">${links.length} inferred port-level dependency link(s).</p>
      <table class="report-table">
        <thead><tr><th>Provider Port</th><th>Require Port</th><th>Inferred Interface</th><th>P-Port Page</th><th>R-Port Page</th><th>Confidence</th></tr></thead>
        <tbody>
          ${links.map(d => `<tr>
            <td><code>${escapeHtml(d.provider_port)}</code></td>
            <td><code>${escapeHtml(d.require_port)}</code></td>
            <td><code>${escapeHtml(d.inferred_iface)}</code></td>
            <td>p.${d.provider_page || '—'}</td>
            <td>p.${d.require_page || '—'}</td>
            <td>${confBadge(d.confidence || 'medium')}</td>
          </tr>`).join('')}
        </tbody>
      </table>
      <p class="report-muted" style="margin-top:.6rem">
        These links are inferred from port naming conventions only.
        They may not reflect actual RTE connections in the implemented system.
      </p>`;
  }

  /* Architecture findings (from Q&A) */
  function renderArchFindings(findings) {
    if (!findings.length) {
      return `
        <p class="report-muted">No Q&A architecture findings recorded.</p>
        <p class="report-muted">Use the <strong>Ask the HLD</strong> tab to ask questions about the document architecture.</p>`;
    }
    return findings.map((f, i) => `
      <div class="report-finding-card">
        <div class="report-finding-header">
          <span class="report-finding-num">Finding ${i + 1}</span>
          ${badge('AI-GENERATED', 'ai')}
        </div>
        <div class="report-finding-q"><strong>Q:</strong> ${escapeHtml(f.question)}</div>
        <div class="report-finding-a">
          <div class="report-finding-a-label">Answer (model: <code>${escapeHtml(f.model || '—')}</code>)</div>
          <div class="report-answer-text">${escapeHtml(f.answer_excerpt || '—')}</div>
        </div>
        ${f.sources && f.sources.length ? `
          <div class="report-sources-label">${badge('EXTRACTED', 'extracted')} Source Evidence</div>
          <table class="report-table report-table--compact">
            <thead><tr><th>Page</th><th>Excerpt</th></tr></thead>
            <tbody>
              ${f.sources.slice(0, 5).map(s => {
                const pg = s.page_num || s.page || '—';
                const txt = trunc(s.text || s.excerpt || '—', 150);
                return `<tr><td>p.${pg}</td><td class="report-excerpt">${escapeHtml(txt)}</td></tr>`;
              }).join('')}
            </tbody>
          </table>` : ''}
      </div>
    `).join('');
  }

  /* Inconsistencies */
  function renderInconsistencies(items, inc_sum) {
    const summaryHtml = `
      <div class="report-inc-summary">
        ${incSummaryPill('warning', 'WARNING', inc_sum.warning || 0)}
        ${incSummaryPill('review', 'REVIEW', inc_sum.review || 0)}
        ${incSummaryPill('info', 'INFO', inc_sum.info || 0)}
        <span class="report-inc-total">Total: ${items.length} finding(s)</span>
      </div>`;

    if (!items.length) {
      return summaryHtml + `
        <div class="report-ok-notice">
          ✓ No document-level inconsistencies detected by the automated rules.
          Manual review is still required.
        </div>`;
    }

    const findingsHtml = items.map((inc, i) => {
      const sev   = (inc.severity || 'info').toLowerCase();
      const pages = (inc.pages || []).map(p => `p.${p}`).join(', ') || '—';
      return `
        <div class="report-inc-card report-inc-card--${sev}">
          <div class="report-inc-card-header">
            <span class="report-inc-num">Finding ${i + 1}</span>
            <span class="severity-badge sev-${sev}">${sev.toUpperCase()}</span>
            <code class="report-inc-cat">${escapeHtml(inc.category || 'general')}</code>
            <span class="report-inc-pages">Pages: ${escapeHtml(pages)}</span>
          </div>
          <div class="report-inc-desc">${escapeHtml(inc.description || '')}</div>
          ${inc.evidence ? `
            <div class="report-inc-evidence-label">${badge('EXTRACTED', 'extracted')} Evidence from Document</div>
            <blockquote class="report-inc-evidence">${escapeHtml(inc.evidence)}</blockquote>
          ` : ''}
          ${inc.reason ? `
            <div class="report-inc-reason">${badge('RULE-BASED', 'rule')} <strong>Why flagged:</strong> ${escapeHtml(inc.reason)}</div>
          ` : ''}
          <div class="report-inc-disposition">
            <strong>Engineer Disposition:</strong>
            <label class="report-checkbox"><input type="checkbox"> Reviewed</label>
            <label class="report-checkbox"><input type="checkbox"> False Positive</label>
            <label class="report-checkbox"><input type="checkbox"> Action Required</label>
          </div>
        </div>`;
    }).join('');

    return summaryHtml + findingsHtml;
  }

  function incSummaryPill(type, label, count) {
    return `<span class="severity-badge sev-${type}">${label}: ${count}</span>`;
  }

  /* Q&A Log */
  function renderQaLog(queries) {
    if (!queries.length) return `<p class="report-muted">No Q&A queries recorded for this document session.</p>`;
    return queries.map((q, i) => `
      <div class="report-qa-card">
        <div class="report-qa-header">
          <span class="report-qa-num">Query ${i + 1}</span>
          <span class="report-qa-meta"><code>${escapeHtml(q.model_used || '—')}</code> · ${escapeHtml(q.created_at || '—')}</span>
        </div>
        <div class="report-qa-question"><strong>Q:</strong> ${escapeHtml(q.question || '—')}</div>
        <div class="report-qa-answer-label">${badge('AI-GENERATED', 'ai')} Answer</div>
        <div class="report-answer-text">${escapeHtml(q.answer || '—')}</div>
        ${q.sources && q.sources.length ? `
          <div class="report-sources-label">${badge('EXTRACTED', 'extracted')} Source Evidence (${q.sources.length} chunk(s) retrieved)</div>
          <table class="report-table report-table--compact">
            <thead><tr><th>Page</th><th>Section</th><th>Excerpt</th></tr></thead>
            <tbody>
              ${q.sources.slice(0, 6).map(s => {
                const pg  = s.page_num || s.page || '—';
                const sec = s.section || '—';
                const txt = trunc(s.text || s.excerpt || '—', 180);
                return `<tr>
                  <td>p.${pg}</td>
                  <td>${escapeHtml(sec)}</td>
                  <td class="report-excerpt">${escapeHtml(txt)}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>` : '<p class="report-muted" style="margin:.4rem 0">No source citations recorded for this query.</p>'}
      </div>`).join('');
  }

  /* Traceability Index */
  function renderTraceability(index) {
    const entries = Object.entries(index)
      .map(([pg, info]) => ({ pg: parseInt(pg, 10), info }))
      .filter(e => e.info.entities?.length || e.info.inconsistencies?.length)
      .sort((a, b) => a.pg - b.pg);

    if (!entries.length) {
      return `<p class="report-muted">No page-entity mappings available. Run entity extraction first.</p>`;
    }

    return `
      <table class="report-table">
        <thead>
          <tr>
            <th>Page</th>
            <th>Entities Detected ${badge('EXTRACTED', 'extracted')}</th>
            <th>Confidence</th>
            <th>Consistency Observations ${badge('RULE-BASED', 'rule')}</th>
          </tr>
        </thead>
        <tbody>
          ${entries.map(({ pg, info }) => {
            const ents = info.entities || [];
            const incs = info.inconsistencies || [];
            const entStr = ents.slice(0, 5).map(e => `<code>${escapeHtml(e.name || '')}</code>`).join(', ')
              + (ents.length > 5 ? ` <em>+${ents.length - 5} more</em>` : '');
            const high = ents.filter(e => e.confidence === 'high').length;
            const low  = ents.filter(e => ['low','uncertain'].includes(e.confidence)).length;
            const confStr = ents.length ? `${ents.length} entity(ies) — ${high} high / ${low} low` : '—';
            const incStr = incs.length ? incs.slice(0, 2).map(i => escapeHtml(trunc(i, 70))).join('; ') : '—';
            return `<tr>
              <td><strong>p.${pg}</strong></td>
              <td>${entStr || '—'}</td>
              <td>${escapeHtml(confStr)}</td>
              <td>${incStr}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  /* Sign-off */
  function renderSignoff(ps, dm, rs) {
    const statusCls = { warning: 'danger', review: 'warning', info: 'info', success: 'success', pending: 'muted' }[rs.color] || 'muted';
    const stageTable = `
      <table class="report-table">
        <thead><tr><th>Stage</th><th>Completed</th><th>Result</th></tr></thead>
        <tbody>
          <tr><td>Document Ingestion</td><td>${dm.status === 'ready' ? '✓' : '✗'}</td><td>${(dm.status || '—').toUpperCase()}</td></tr>
          <tr><td>Entity Extraction</td><td>${ps.extraction_performed ? '✓' : '○ Pending'}</td><td>${ps.total_entities_found || 0} entities found</td></tr>
          <tr><td>Consistency Check</td><td>${ps.consistency_checked ? '✓' : '○ Pending'}</td><td>${(ps.inconsistency_count || 0)} findings</td></tr>
          <tr><td>Q&A Review</td><td>${ps.qa_sessions > 0 ? '✓' : '○ No queries'}</td><td>${ps.qa_sessions || 0} queries</td></tr>
          <tr><td><strong>Overall</strong></td><td></td><td class="report-status-cell report-status-cell--${statusCls}"><strong>${escapeHtml(rs.overall || '—')}</strong></td></tr>
        </tbody>
      </table>`;

    const signoffTable = `
      <h4 class="report-subheading" style="margin-top:1.4rem">Human Engineering Sign-off</h4>
      <p class="report-muted">Complete this section after reviewing all findings above.</p>
      <table class="report-table">
        <thead><tr><th>Role</th><th>Engineer Name</th><th>Date</th><th>Disposition</th></tr></thead>
        <tbody>
          ${[
            'Lead Systems Architect',
            'Software Safety Engineer',
            'AUTOSAR Integration Engineer',
            'Review Coordinator',
          ].map(role => `<tr>
            <td>${escapeHtml(role)}</td>
            <td><input type="text" class="report-signoff-input" placeholder="Name"></td>
            <td><input type="text" class="report-signoff-input report-signoff-input--date" placeholder="DD-MMM-YYYY"></td>
            <td>
              <select class="report-signoff-select">
                <option value="">— Select —</option>
                <option>Approved</option>
                <option>Revision Required</option>
                <option>Rejected</option>
                ${role === 'Review Coordinator' ? '<option>Released</option><option>Withheld</option>' : ''}
              </select>
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
      <div style="margin-top:1rem">
        <label class="report-subheading">Review Notes</label>
        <textarea class="report-notes-area" placeholder="Enter engineer review notes here…"></textarea>
      </div>`;

    return stageTable + signoffTable;
  }

  /* ── Utilities ─────────────────────────────────────────────────────────── */

  function dataTable(rows) {
    return `
      <table class="report-table">
        <tbody>
          ${rows.map(([k, v]) => `<tr><th style="width:38%">${escapeHtml(k)}</th><td>${v}</td></tr>`).join('')}
        </tbody>
      </table>`;
  }

  function confBadge(level) {
    const cls = { high: 'success', medium: 'info', low: 'warning', uncertain: 'danger' }[level] || 'muted';
    return `<span class="conf-badge conf-badge--${cls}">${level}</span>`;
  }

  function trunc(str, n) {
    if (!str) return '—';
    str = String(str).replace(/\s+/g, ' ').trim();
    return str.length <= n ? str : str.slice(0, n) + '…';
  }

  function renderEmpty() {
    currentMarkdown = '';
    currentReportData = null;
    if (preview) {
      preview.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📋</div>
          <div>Select a document, then click <strong>Generate Report</strong>.</div>
        </div>`;
    }
    if (downloadBtn) downloadBtn.href = '#';
  }

  function renderError(msg) {
    if (preview) {
      preview.innerHTML = `
        <div class="empty-state" style="color:var(--danger)">
          <div class="empty-state-icon">⚠</div>
          <div>Failed to generate report: ${escapeHtml(msg)}</div>
        </div>`;
    }
  }

  function setGenerating(on) {
    if (!generateBtn) return;
    generateBtn.disabled = on;
    generateBtn.innerHTML = on
      ? '<span class="spinner"></span> Building…'
      : 'Generate Report';
  }

  return { init, refresh };
})();
