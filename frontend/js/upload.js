/**
 * upload.js — Logic for the "My Documents" page: upload, progress, and document list.
 */

window.UploadModule = (() => {
  const uploadZone     = document.getElementById('upload-zone');
  const fileInput      = document.getElementById('file-input');
  const progressWrap   = document.getElementById('upload-progress-wrap');
  const progressFill   = document.getElementById('upload-progress-fill');
  const uploadFileName = document.getElementById('upload-file-name');
  const uploadStatus   = document.getElementById('upload-status-text');
  const uploadDetail   = document.getElementById('upload-step-detail');
  const registryBody   = document.getElementById('doc-registry-body');

  function init() {
    setupDropzone();
    setupRegistryRefresh();
    refreshDocRegistry();
  }

  function setupDropzone() {
    if (!uploadZone || !fileInput) return;

    uploadZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', (e) => {
      // Only remove if leaving the zone entirely
      if (!uploadZone.contains(e.relatedTarget)) {
        uploadZone.classList.remove('drag-over');
      }
    });

    uploadZone.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadZone.classList.remove('drag-over');
      const files = e.dataTransfer.files;
      if (files.length > 0) handleFile(files[0]);
    });

    uploadZone.addEventListener('click', (e) => {
      if (e.target.tagName !== 'LABEL') fileInput.click();
    });

    uploadZone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
      }
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
    });
  }

  function setupRegistryRefresh() {
    document.getElementById('refresh-docs-btn')?.addEventListener('click', () => {
      refreshDocRegistry();
      showToast('Document list refreshed', 'info');
    });
  }

  async function handleFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      showToast('Please upload a PDF file. Other formats are not supported.', 'error');
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      showToast('File is too large. Maximum size is 50 MB.', 'error');
      return;
    }

    // Show progress
    progressWrap.classList.remove('hidden');
    if (uploadFileName) uploadFileName.textContent = file.name;
    if (uploadStatus) uploadStatus.textContent = 'Uploading…';
    if (uploadDetail) uploadDetail.textContent = 'Sending file to the server…';
    if (progressFill) progressFill.style.width = '20%';

    try {
      const resp = await API.uploadDocument(file);
      const docId = resp.doc_id;

      if (progressFill) progressFill.style.width = '50%';
      if (uploadStatus) uploadStatus.textContent = 'Reading document…';
      if (uploadDetail) uploadDetail.textContent = 'Reading document pages and preparing searchable content…';

      await pollIngestStatus(docId, file.name);
    } catch (err) {
      if (progressWrap) progressWrap.classList.add('hidden');
      showToast(`Upload failed: ${err.message}`, 'error', 5000);
    }
  }

  async function pollIngestStatus(docId, filename) {
    const startTime = Date.now();
    const interval = 1000;

    const timer = setInterval(async () => {
      try {
        const res = await API.pollStatus(docId);

        if (res.status === 'ready') {
          clearInterval(timer);
          if (progressFill) progressFill.style.width = '100%';
          if (uploadStatus) uploadStatus.textContent = 'Ready';
          if (uploadDetail) {
            uploadDetail.textContent = `Done. ${res.page_count} pages processed.`;
          }

          showToast(`"${filename}" is ready to explore.`, 'success');

          await refreshDocSelector(false);
          await refreshDocRegistry();
          selectDocument(docId, filename, res);

          // Update home doc list
          if (window.HomeModule?.refresh) await window.HomeModule.refresh();

          setTimeout(() => {
            if (progressWrap) progressWrap.classList.add('hidden');
            if (progressFill) progressFill.style.width = '0%';
          }, 4000);

        } else if (res.status === 'error') {
          clearInterval(timer);
          if (uploadStatus) uploadStatus.textContent = 'Processing failed';
          if (uploadDetail) {
            uploadDetail.textContent = res.error_msg || 'The document could not be processed. Please try again.';
          }
          showToast(`Could not process "${filename}": ${res.error_msg || 'Unknown error'}`, 'error', 6000);

        } else {
          // Still processing
          const elapsed = Date.now() - startTime;
          const pct = Math.min(90, 50 + Math.floor(elapsed / 500));
          if (progressFill) progressFill.style.width = `${pct}%`;
        }

      } catch (err) {
        clearInterval(timer);
        if (uploadStatus) uploadStatus.textContent = 'Check failed';
        if (uploadDetail) uploadDetail.textContent = err.message;
      }
    }, interval);
  }

  async function refreshDocRegistry() {
    if (!registryBody) return;

    try {
      const data = await API.listDocuments();
      const docs = Array.isArray(data) ? data : (data.documents || []);

      if (docs.length === 0) {
        registryBody.innerHTML = `
          <tr><td colspan="5" class="table-empty">No documents uploaded yet. Upload a PDF to get started.</td></tr>
        `;
        return;
      }

      registryBody.innerHTML = docs.map(d => {
        const isCurrent = d.doc_id === App.currentDocId;
        let statusBadge;
        if (d.needs_repair) {
          statusBadge = '<span class="badge badge-warning">Needs Repair</span>';
        } else if (d.status === 'ready') {
          statusBadge = '<span class="badge badge-success">Ready</span>';
        } else if (d.status === 'error') {
          statusBadge = '<span class="badge badge-warning" title="' + escapeHtml(d.error_msg || '') + '">Error</span>';
        } else {
          statusBadge = `<span class="badge badge-warning">${d.status}</span>`;
        }
        const uploadDate = d.upload_time ? new Date(d.upload_time).toLocaleString() : '—';

        return `
          <tr style="${isCurrent ? 'background-color: var(--accent-muted);' : ''}">
            <td style="font-weight: 600;">${escapeHtml(d.filename)}</td>
            <td>${d.page_count ?? '—'}</td>
            <td style="color: var(--text-muted); font-size: 12px;">${uploadDate}</td>
            <td>${statusBadge}</td>
            <td>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                ${d.status === 'ready' && !d.needs_repair ? `
                  <button
                    class="btn btn-sm ${isCurrent ? 'btn-primary' : 'btn-ghost'}"
                    onclick="UploadModule.selectDoc('${d.doc_id}', '${escapeHtml(d.filename)}')"
                    ${isCurrent ? 'aria-current="true"' : ''}
                  >
                    ${isCurrent ? 'Active' : 'Select'}
                  </button>
                ` : ''}
                ${d.needs_repair ? `
                  <button
                    class="btn btn-sm btn-primary"
                    onclick="UploadModule.repairDoc('${d.doc_id}', '${escapeHtml(d.filename)}')"
                    title="Re-index this document in the vector store"
                  >
                    ⚡ Repair
                  </button>
                ` : ''}
                <button
                  class="btn btn-sm btn-danger"
                  onclick="UploadModule.deleteDoc('${d.doc_id}', '${escapeHtml(d.filename)}')"
                  aria-label="Delete ${escapeHtml(d.filename)}"
                >
                  Delete
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      registryBody.innerHTML = `
        <tr><td colspan="5" class="table-empty" style="color: var(--danger);">Could not load documents: ${err.message}</td></tr>
      `;
    }
  }

  async function selectDoc(docId, filename) {
    const docs = await API.listDocuments();
    const docList = Array.isArray(docs) ? docs : (docs.documents || []);
    const meta = docList.find(d => d.doc_id === docId) || null;

    selectDocument(docId, filename, meta);
    await refreshDocRegistry();
    if (window.HomeModule?.refresh) await window.HomeModule.refresh();
    showToast(`Now viewing: ${filename}`, 'info');
  }

  async function deleteDoc(docId, filename) {
    if (!confirm(`Delete "${filename}"? This will remove all processed data for this document.`)) {
      return;
    }

    try {
      await API.deleteDocument(docId);
      showToast(`"${filename}" deleted.`, 'info');

      if (App.currentDocId === docId) {
        selectDocument(null, null);
      }

      await refreshDocSelector(true);
      await refreshDocRegistry();
      if (window.HomeModule?.refresh) await window.HomeModule.refresh();
    } catch (err) {
      showToast(`Could not delete: ${err.message}`, 'error');
    }
  }

  async function repairDoc(docId, filename) {
    if (!confirm(`Re-index "${filename}"? This will re-process the PDF and rebuild the vector store. It may take 30–60 seconds.`)) {
      return;
    }

    try {
      showToast(`Re-indexing "${filename}"…`, 'info', 8000);
      await API.repairDocument(docId);

      // Poll for completion just like a normal upload
      await pollIngestStatus(docId, filename);

      await refreshDocSelector(false);
      await refreshDocRegistry();
      if (window.HomeModule?.refresh) await window.HomeModule.refresh();
    } catch (err) {
      showToast(`Repair failed: ${err.message}`, 'error', 6000);
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;');
  }

  // Bootstrap
  init();

  return {
    selectDoc,
    deleteDoc,
    repairDoc,
    refreshDocRegistry,
  };
})();
