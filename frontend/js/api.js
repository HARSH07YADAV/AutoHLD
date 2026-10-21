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

  async function uploadSampleDocument() {
    return _request('POST', '/api/upload/sample');
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

  async function askQuestionStream(docId, question, { onToken, onSources, onDone, onError }) {
    let resp;
    try {
      resp = await fetch(`${BASE}/api/ask/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, question }),
      });
    } catch (netErr) {
      if (onError) onError(new Error(`Connection failed: ${netErr.message}`));
      return;
    }

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        detail = err.detail || detail;
      } catch (_) {}
      const errorObj = new Error(detail);
      if (onError) onError(errorObj);
      else throw errorObj;
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop(); // keep trailing incomplete event block

        for (const block of parts) {
          if (!block.trim()) continue;
          let event = 'message';
          let dataStr = '';
          for (const line of block.split('\n')) {
            if (line.startsWith('event:')) {
              event = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              dataStr += line.slice(5).trim();
            }
          }

          if (!dataStr) continue;
          try {
            const data = JSON.parse(dataStr);
            if (event === 'sources' && onSources) {
              onSources(data.sources, data.retrieval_time_s);
            } else if (event === 'token' && onToken) {
              onToken(data.token);
            } else if (event === 'done' && onDone) {
              onDone(data);
            } else if (event === 'error') {
              if (onError) onError(new Error(data.error || 'Inference error'));
              return;
            }
          } catch (jsonErr) {
            console.error('Error parsing SSE event payload:', jsonErr, block);
          }
        }
      }
    } catch (streamErr) {
      if (onError) onError(streamErr);
      else throw streamErr;
    }
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

  async function repairDocument(docId) {
    return _request('POST', `/api/repair/${docId}`);
  }

  async function getEDA(docId) {
    return _request('GET', `/api/eda/${docId}`);
  }

  function getReportDownloadUrl(docId) {
    return `${BASE}/api/reports/${docId}/download`;
  }

  return {
    uploadDocument,
    uploadSampleDocument,
    pollStatus,
    listDocuments,
    deleteDocument,
    repairDocument,
    askQuestion,
    askQuestionStream,
    getHistory,
    getLLMStatus,
    extractEntities,
    getRelationships,
    runConsistencyCheck,
    getInconsistencyReport,
    getDashboardData,
    getReport,
    getEDA,
    getReportDownloadUrl,
  };
})();

if (typeof window !== 'undefined') {
  window.API = API;
  window.API.askQuestionStream = API.askQuestionStream;
}

