/**
 * api.js — All HTTP calls to the FastAPI backend.
 *
 * One function per endpoint. Every function returns a parsed JSON object
 * or throws an Error with a user-readable message.
 */

const API = (() => {
  const BASE = '';  // same origin

  async function _request(method, path, body = null) {
    const opts = {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
    };
    if (body) opts.body = JSON.stringify(body);

    const resp = await fetch(BASE + path, opts);
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        detail = err.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    return resp.json();
  }

  async function uploadDocument(file) {
    const form = new FormData();
    form.append('file', file);
    const resp = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { const e = await resp.json(); detail = e.detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return resp.json();
  }

  async function pollStatus(docId) {
    return _request('GET', `/api/status/${docId}`);
  }

  async function listDocuments() {
    return _request('GET', '/api/documents');
  }

  async function askQuestion(docId, question) {
    return _request('POST', '/api/ask', { doc_id: docId, question });
  }

  async function getHistory(docId) {
    return _request('GET', `/api/history/${docId}`);
  }

  async function getLLMStatus() {
    return _request('GET', '/api/llm/status');
  }

  async function extractEntities(docId) {
    return _request('POST', `/api/extract/${docId}`);
  }

  async function getRelationships(docId) {
    return _request('GET', `/api/relationships/${docId}`);
  }

  async function runConsistencyCheck(docId) {
    return _request('POST', `/api/inconsistencies/${docId}`);
  }

  async function getInconsistencyReport(docId) {
    return _request('GET', `/api/inconsistency-report/${docId}`);
  }

  async function getDashboardData(docId) {
    return _request('GET', `/api/dashboard/${docId}`);
  }

  async function getReport(docId) {
    return _request('GET', `/api/reports/${docId}`);
  }

  async function deleteDocument(docId) {
    return _request('DELETE', `/api/documents/${docId}`);
  }

  function getReportDownloadUrl(docId) {
    return `${BASE}/api/reports/${docId}/download`;
  }

  return {
    uploadDocument,
    pollStatus,
    listDocuments,
    deleteDocument,
    askQuestion,
    getHistory,
    getLLMStatus,
    extractEntities,
    getRelationships,
    runConsistencyCheck,
    getInconsistencyReport,
    getDashboardData,
    getReport,
    getReportDownloadUrl,
  };
})();
