/**
 * query.js — Logic for "Ask a Question" page (Grounded Q&A with Source Citations).
 */

window.QueryModule = (() => {
  const qaInput      = document.getElementById('qa-input');
  const qaSubmitBtn  = document.getElementById('qa-submit-btn');
  const qaLoading    = document.getElementById('qa-loading');
  const qaContainer  = document.getElementById('qa-answer-container');
  const qaAnswerText = document.getElementById('qa-answer-text');
  const qaMetaModel  = document.getElementById('qa-meta-model');
  const citationsGrid= document.getElementById('qa-citations-grid');
  const historyBody  = document.getElementById('qa-history-body');
  const noDocNotice  = document.getElementById('qa-no-doc-notice');

  function init() {
    qaSubmitBtn?.addEventListener('click', () => submitQuestion());
    qaInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        submitQuestion();
      }
    });

    // Suggestion chips
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const q = chip.dataset.q;
        if (q && qaInput) {
          qaInput.value = q;
          submitQuestion();
        }
      });
    });
  }

  async function refresh() {
    await refreshHistory();
    updateNoDocNotice();
  }

  function updateNoDocNotice() {
    if (!noDocNotice) return;
    noDocNotice.style.display = App.currentDocId ? 'none' : 'flex';
  }

  async function submitQuestion() {
    const docId = App.currentDocId;
    if (!docId) {
      if (noDocNotice) noDocNotice.style.display = 'flex';
      showToast('Please select or upload a document first.', 'error');
      return;
    }

    const question = (qaInput?.value || '').trim();
    if (!question) {
      showToast('Please type a question before submitting.', 'error');
      return;
    }

    // Loading state
    if (qaLoading) qaLoading.classList.remove('hidden');
    if (qaContainer) qaContainer.classList.add('hidden');
    if (qaSubmitBtn) qaSubmitBtn.disabled = true;

    try {
      const data = await API.askQuestion(docId, question);
      if (qaLoading) qaLoading.classList.add('hidden');
      renderAnswer(data);
      await refreshHistory();
    } catch (err) {
      if (qaLoading) qaLoading.classList.add('hidden');
      showToast(`Could not get an answer: ${err.message}`, 'error', 5000);
    } finally {
      if (qaSubmitBtn) qaSubmitBtn.disabled = false;
    }
  }

  function renderAnswer(data) {
    if (!qaContainer) return;
    qaContainer.classList.remove('hidden');

    if (qaAnswerText) {
      qaAnswerText.textContent = data.answer || 'No answer was generated. Please try rephrasing your question.';
    }

    if (qaMetaModel) {
      const model = data.model_used || '';
      qaMetaModel.textContent = model ? `AI model: ${model}` : '';
    }

    // Citations
    const citations = data.sources || [];
    if (!citationsGrid) return;

    if (citations.length === 0) {
      citationsGrid.innerHTML = `
        <div style="color: var(--text-muted); font-size: 13px; grid-column: 1/-1; padding: 4px 0;">
          No specific pages were cited for this answer. The response may be based on general content from the document.
        </div>
      `;
    } else {
      citationsGrid.innerHTML = citations.map(c => `
        <div class="citation-card">
          <div class="citation-head">
            <span class="badge-page">Page ${c.page_num || c.page || '—'}</span>
            <span class="citation-section-label">${c.section ? escapeHtml(c.section) : 'Document excerpt'}</span>
          </div>
          <div class="citation-excerpt">${escapeHtml(c.text || c.excerpt || '(No excerpt available)')}</div>
        </div>
      `).join('');
    }
  }

  async function refreshHistory() {
    const docId = App.currentDocId;
    if (!docId || !historyBody) return;

    try {
      const data = await API.getHistory(docId);
      const items = Array.isArray(data) ? data : (data.history || []);

      if (items.length === 0) {
        historyBody.innerHTML = `
          <tr><td colspan="3" class="table-empty">No questions asked yet. Use the question box above to start.</td></tr>
        `;
        return;
      }

      historyBody.innerHTML = items.map(item => `
        <tr>
          <td style="color: var(--text-muted); font-size: 12px; white-space: nowrap;">
            ${item.created_at ? new Date(item.created_at).toLocaleTimeString() : '—'}
          </td>
          <td style="font-weight: 500;">${escapeHtml(item.question)}</td>
          <td>
            ${(item.sources || []).length > 0
              ? `<span class="badge badge-accent">${(item.sources || []).length} pages</span>`
              : '<span style="color: var(--text-muted); font-size: 12px;">—</span>'
            }
          </td>
        </tr>
      `).join('');
    } catch (err) {
      console.warn('Failed to load question history:', err);
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  init();

  return { refresh };
})();
