/**
 * query.js — ChatGPT-Style Conversational Technical Q&A with Collapsible History Sidebar.
 * Preserves chat history and maintains separate conversations.
 */

window.QueryModule = (() => {
  const qaInput          = document.getElementById('qa-input');
  const qaSubmitBtn      = document.getElementById('qa-submit-btn');
  const qaLoading        = document.getElementById('qa-loading');
  const noDocNotice      = document.getElementById('qa-no-doc-notice');
  const chatStream       = document.getElementById('qa-chat-stream');
  const historyList      = document.getElementById('qa-history-list');
  const historyCount     = document.getElementById('qa-history-count');
  const activeChatTitle  = document.getElementById('qa-active-chat-title');
  const historySearch    = document.getElementById('qa-history-search');
  const workspace        = document.getElementById('qa-workspace');

  let activeConversationId = null;
  let conversations = [];

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
    loadLocalConversations();
    await syncWithBackendHistory();
    updateNoDocNotice();
  }

  function updateNoDocNotice() {
    if (!noDocNotice) return;
    noDocNotice.style.display = App.currentDocId ? 'none' : 'flex';
  }

  function getStorageKey() {
    return `autohld_conversations_${App.currentDocId || 'global'}`;
  }

  function loadLocalConversations() {
    if (!App.currentDocId) {
      conversations = [];
      renderHistoryList([]);
      return;
    }
    try {
      const stored = localStorage.getItem(getStorageKey());
      conversations = stored ? JSON.parse(stored) : [];
    } catch (_) {
      conversations = [];
    }
  }

  function saveLocalConversations() {
    if (!App.currentDocId) return;
    try {
      localStorage.setItem(getStorageKey(), JSON.stringify(conversations));
    } catch (_) {}
  }

  async function syncWithBackendHistory() {
    const docId = App.currentDocId;
    if (!docId) {
      renderHistoryList([]);
      return;
    }

    try {
      const data = await API.getHistory(docId);
      const items = Array.isArray(data) ? data : (data.history || []);

      // Import any backend SQLite queries that are not in local storage
      let modified = false;
      for (const item of items) {
        const legacyId = `sqlite_${item.id}`;
        const exists = conversations.some(c => c.id === legacyId || c.title === item.question);
        if (!exists) {
          conversations.push({
            id: legacyId,
            title: item.question,
            created_at: item.created_at || new Date().toISOString(),
            messages: [
              {
                role: 'user',
                text: item.question,
                time: item.created_at ? new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '',
              },
              {
                role: 'assistant',
                text: item.answer,
                model: item.model_used || 'Local LLM',
                sources: item.sources || [],
                time: item.created_at ? new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '',
              }
            ]
          });
          modified = true;
        }
      }

      if (modified) {
        // Sort conversations newest first
        conversations.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        saveLocalConversations();
      }

      renderHistoryList(conversations);

      // If no conversation is active yet, load the most recent one if available
      if (!activeConversationId && conversations.length > 0) {
        loadConversation(conversations[0].id);
      } else if (!activeConversationId) {
        renderWelcomeScreen();
      }
    } catch (err) {
      console.warn('Could not sync with backend history:', err);
      renderHistoryList(conversations);
    }
  }

  function toggleHistorySidebar() {
    if (workspace) {
      workspace.classList.toggle('sidebar-collapsed');
    }
  }

  function startNewChat() {
    activeConversationId = null;
    renderWelcomeScreen();
    if (activeChatTitle) {
      activeChatTitle.textContent = 'AutoHLD Engineering Assistant';
    }
    document.querySelectorAll('.qa-history-item').forEach(el => el.classList.remove('active'));
    if (qaInput) {
      qaInput.value = '';
      qaInput.focus();
    }
    showToast('Started new conversation', 'info');
  }

  function renderWelcomeScreen() {
    if (!chatStream) return;
    chatStream.innerHTML = `
      <div class="chat-msg chat-msg--assistant">
        <div class="chat-avatar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/></svg>
        </div>
        <div class="chat-bubble">
          <div class="chat-sender">AutoHLD Engineering Assistant</div>
          <div class="chat-text">
            <p>Welcome to the AutoHLD technical assistant. I analyze the active specification using semantic vector retrieval and synthesize grounded answers with explicit page references.</p>
            <p>Select a template above or type your technical question below to explore system components, interfaces, and port definitions.</p>
          </div>
        </div>
      </div>
    `;
  }

  function clearChat() {
    startNewChat();
  }

  function clearAllConversations() {
    if (!confirm('Are you sure you want to clear all conversation history for this document?')) return;
    conversations = [];
    activeConversationId = null;
    saveLocalConversations();
    renderHistoryList([]);
    renderWelcomeScreen();
    if (activeChatTitle) {
      activeChatTitle.textContent = 'AutoHLD Engineering Assistant';
    }
    showToast('Conversation history cleared', 'info');
  }

  function loadConversation(convId) {
    const conv = conversations.find(c => c.id === convId);
    if (!conv) return;

    activeConversationId = convId;

    // Highlight active item in sidebar
    document.querySelectorAll('.qa-history-item').forEach(el => {
      el.classList.toggle('active', el.dataset.id === String(convId));
    });

    if (activeChatTitle) {
      activeChatTitle.textContent = conv.title || 'Conversation';
    }

    if (!chatStream) return;
    chatStream.innerHTML = '';

    // Render all messages in this conversation
    (conv.messages || []).forEach(msg => {
      if (msg.role === 'user') {
        renderUserBubble(msg.text);
      } else {
        renderAssistantBubble(msg.text, msg.model, msg.sources);
      }
    });

    chatStream.scrollTop = chatStream.scrollHeight;
  }

  function deleteConversation(convId, event) {
    if (event) event.stopPropagation();
    conversations = conversations.filter(c => c.id !== convId);
    saveLocalConversations();
    renderHistoryList(conversations);

    if (activeConversationId === convId) {
      if (conversations.length > 0) {
        loadConversation(conversations[0].id);
      } else {
        startNewChat();
      }
    }
    showToast('Conversation removed', 'info');
  }

  function renderHistoryList(items) {
    if (!historyList) return;

    if (historyCount) {
      historyCount.textContent = String(conversations.length);
    }

    if (!items || items.length === 0) {
      historyList.innerHTML = `
        <div class="qa-history-empty">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span>No chat history yet</span>
          <p>Questions asked about this specification will appear here.</p>
        </div>
      `;
      return;
    }

    historyList.innerHTML = items.map(conv => {
      const titleEscaped = escapeHtml(conv.title);
      const timeStr = conv.created_at ? new Date(conv.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '';
      const msgCount = (conv.messages || []).length;
      const isActive = activeConversationId === conv.id;

      return `
        <div class="qa-history-item ${isActive ? 'active' : ''}" data-id="${conv.id}" onclick="QueryModule.loadConversation('${conv.id}')" title="${titleEscaped}">
          <div class="qa-history-item-left">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            <div class="qa-history-item-content">
              <span class="qa-history-item-title">${titleEscaped}</span>
              <div class="qa-history-item-sub">
                <span>${timeStr}</span>
                <span>·</span>
                <span>${msgCount} msg${msgCount === 1 ? '' : 's'}</span>
              </div>
            </div>
          </div>
          <div class="qa-history-item-actions">
            <button class="qa-history-del-btn" onclick="QueryModule.deleteConversation('${conv.id}', event)" title="Delete conversation" aria-label="Delete conversation">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  function filterHistory(query) {
    const q = (query || '').toLowerCase().trim();
    if (!q) {
      renderHistoryList(conversations);
      return;
    }
    const filtered = conversations.filter(c => (c.title || '').toLowerCase().includes(q));
    renderHistoryList(filtered);
  }

  async function executeStream(docId, question, callbacks) {
    if (typeof API !== 'undefined' && typeof API.askQuestionStream === 'function') {
      return API.askQuestionStream(docId, question, callbacks);
    }
    if (typeof window !== 'undefined' && typeof window.askQuestionStream === 'function') {
      return window.askQuestionStream(docId, question, callbacks);
    }

    // Direct fallback if api.js was cached by the browser
    let resp;
    try {
      resp = await fetch('/api/ask/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, question }),
      });
    } catch (netErr) {
      if (callbacks.onError) callbacks.onError(new Error(`Connection failed: ${netErr.message}`));
      return;
    }

    if (!resp.ok) {
      if (typeof API !== 'undefined' && typeof API.askQuestion === 'function') {
        try {
          const fullResp = await API.askQuestion(docId, question);
          if (callbacks.onSources) callbacks.onSources(fullResp.sources || [], 0);
          if (callbacks.onToken) callbacks.onToken(fullResp.answer || '');
          if (callbacks.onDone) callbacks.onDone(fullResp);
          return;
        } catch (fallbackErr) {
          if (callbacks.onError) callbacks.onError(fallbackErr);
          else throw fallbackErr;
          return;
        }
      }
      let detail = `HTTP ${resp.status}`;
      try { const err = await resp.json(); detail = err.detail || detail; } catch (_) {}
      const errorObj = new Error(detail);
      if (callbacks.onError) callbacks.onError(errorObj);
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
        buffer = parts.pop();

        for (const block of parts) {
          if (!block.trim()) continue;
          let event = 'message';
          let dataStr = '';
          for (const line of block.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
          }
          if (!dataStr) continue;
          try {
            const data = JSON.parse(dataStr);
            if (event === 'sources' && callbacks.onSources) {
              callbacks.onSources(data.sources, data.retrieval_time_s);
            } else if (event === 'token' && callbacks.onToken) {
              callbacks.onToken(data.token);
            } else if (event === 'done' && callbacks.onDone) {
              callbacks.onDone(data);
            } else if (event === 'error') {
              if (callbacks.onError) callbacks.onError(new Error(data.error || 'Inference error'));
              return;
            }
          } catch (jsonErr) {
            console.error('Error parsing SSE payload:', jsonErr);
          }
        }
      }
    } catch (streamErr) {
      if (callbacks.onError) callbacks.onError(streamErr);
      else throw streamErr;
    }
  }

  async function submitQuestion() {
    const docId = App.currentDocId;
    if (!docId) {
      if (noDocNotice) noDocNotice.style.display = 'flex';
      showToast('Please select or upload an HLD document first.', 'error');
      return;
    }

    const question = (qaInput?.value || '').trim();
    if (!question) {
      showToast('Please type a question before submitting.', 'error');
      return;
    }

    // Determine target conversation (existing or new)
    let currentConv = conversations.find(c => c.id === activeConversationId);
    if (!currentConv) {
      // Create new conversation
      const newId = `conv_${Date.now()}`;
      currentConv = {
        id: newId,
        title: question,
        created_at: new Date().toISOString(),
        messages: []
      };
      conversations.unshift(currentConv);
      activeConversationId = newId;
    }

    // Append user question
    currentConv.messages.push({
      role: 'user',
      text: question,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });
    saveLocalConversations();
    renderHistoryList(conversations);

    if (activeChatTitle) {
      activeChatTitle.textContent = currentConv.title;
    }

    // Append to UI
    renderUserBubble(question);
    if (qaInput) qaInput.value = '';

    // Show loading immediately
    if (qaLoading) qaLoading.classList.remove('hidden');
    if (qaSubmitBtn) qaSubmitBtn.disabled = true;

    // Create assistant bubble in DOM for real-time streaming
    const assistantMsg = document.createElement('div');
    assistantMsg.className = 'chat-msg chat-msg--assistant';
    assistantMsg.innerHTML = `
      <div class="chat-avatar" title="AutoHLD AI">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/></svg>
      </div>
      <div class="chat-bubble">
        <div class="card-header-flex" style="margin-bottom: 8px;">
          <div class="chat-sender">AutoHLD Engineering Assistant · <span class="assistant-model-tag" style="color:var(--text-muted); font-weight:normal;">Local LLM</span></div>
          <button class="btn btn-ghost btn-sm copy-btn" style="display:none;">Copy Answer</button>
        </div>

        <div class="grounding-notice-container" style="display:none;"></div>

        <div class="chat-text">
          <span class="stream-text"></span><span class="streaming-cursor">▍</span>
        </div>

        <div class="sources-section" style="display:none; margin-top: 14px; border-top: 1px solid var(--border-subtle); padding-top: 10px;">
          <div class="sources-header-title" style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">
            Verified Document Citations
          </div>
          <div class="sources-grid"></div>
        </div>

        <div class="timing-metrics-bar" style="display:none; margin-top: 12px; gap: 8px; flex-wrap: wrap; align-items: center;"></div>
      </div>
    `;
    chatStream.appendChild(assistantMsg);
    chatStream.scrollTop = chatStream.scrollHeight;

    const streamTextEl = assistantMsg.querySelector('.stream-text');
    const cursorEl = assistantMsg.querySelector('.streaming-cursor');
    const modelTagEl = assistantMsg.querySelector('.assistant-model-tag');
    const copyBtnEl = assistantMsg.querySelector('.copy-btn');
    const sourcesSectionEl = assistantMsg.querySelector('.sources-section');
    const sourcesGridEl = assistantMsg.querySelector('.sources-grid');
    const sourcesTitleEl = assistantMsg.querySelector('.sources-header-title');
    const noticeContainerEl = assistantMsg.querySelector('.grounding-notice-container');
    const timingBarEl = assistantMsg.querySelector('.timing-metrics-bar');

    let accumulatedTokens = '';
    let currentSources = [];
    let hasReceivedTokens = false;

    try {
      await executeStream(docId, question, {
        onSources: (sources, retrievalTime) => {
          if (qaLoading) qaLoading.classList.add('hidden');
          currentSources = sources || [];
          if (currentSources.length > 0 && sourcesSectionEl && sourcesGridEl) {
            sourcesSectionEl.style.display = 'block';
            sourcesTitleEl.textContent = `Retrieved Evidence Chunks (${currentSources.length})`;
            sourcesGridEl.innerHTML = buildCitationsHtml(currentSources, false);
            chatStream.scrollTop = chatStream.scrollHeight;
          }
        },
        onToken: (token) => {
          if (qaLoading) qaLoading.classList.add('hidden');
          hasReceivedTokens = true;
          accumulatedTokens += token;
          if (streamTextEl) {
            streamTextEl.textContent = accumulatedTokens;
          }
          chatStream.scrollTop = chatStream.scrollHeight;
        },
        onDone: (data) => {
          if (qaLoading) qaLoading.classList.add('hidden');
          if (qaSubmitBtn) qaSubmitBtn.disabled = false;
          if (cursorEl) cursorEl.remove();

          const finalAnswer = data.answer || accumulatedTokens || 'No answer generated.';
          const finalModel = data.model || 'Local LLM';
          const finalSources = data.sources || currentSources || [];

          // Format final text with markdown & citations
          if (streamTextEl) {
            streamTextEl.innerHTML = formatAnswer(finalAnswer);
          }

          if (modelTagEl) {
            modelTagEl.textContent = finalModel;
          }

          // Check if not found
          const isNotFound = /this information was not found in the selected document|not found in the selected document|no information regarding|not specified in the selected document/i.test(finalAnswer);
          if (isNotFound && noticeContainerEl) {
            noticeContainerEl.style.display = 'block';
            noticeContainerEl.innerHTML = `
              <div class="grounding-notice">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <div><strong>Specification Scope Notice:</strong> The requested technical detail was not found in the currently selected document.</div>
              </div>
            `;
          }

          // Render citations
          if (sourcesSectionEl && sourcesGridEl) {
            sourcesSectionEl.style.display = 'block';
            sourcesTitleEl.textContent = (finalSources && finalSources.length > 0)
              ? `Verified Document Citations (${finalSources.length})`
              : 'Source Evidence';
            sourcesGridEl.innerHTML = buildCitationsHtml(finalSources, isNotFound);
          }

          // Copy button
          if (copyBtnEl) {
            copyBtnEl.style.display = 'inline-flex';
            copyBtnEl.onclick = () => {
              navigator.clipboard.writeText(finalAnswer);
              showToast('Answer copied', 'info');
            };
          }

          // Display timing metrics pill
          if (data.timings && timingBarEl) {
            timingBarEl.style.display = 'flex';
            const t = data.timings;
            timingBarEl.innerHTML = `
              <span class="qa-metrics-badge" title="ChromaDB semantic search + BM25 keyword matching">
                ⚡ Retrieval: <strong>${Math.round((t.retrieval_s || 0) * 1000)}ms</strong>
              </span>
              <span class="qa-metrics-badge" title="Time to first streamed token">
                🚀 TTFT: <strong>${t.ttft_s || 0}s</strong>
              </span>
              <span class="qa-metrics-badge" title="Generation speed in tokens per second">
                ⚡ Speed: <strong>${t.tokens_per_sec || 0} tok/s</strong>
              </span>
              <span class="qa-metrics-badge" title="Total response latency from click to complete answer">
                ⏱ Total: <strong>${t.total_s || 0}s</strong>
              </span>
            `;
          }

          // Save to active conversation
          currentConv.messages.push({
            role: 'assistant',
            text: finalAnswer,
            model: finalModel,
            sources: finalSources,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          });
          saveLocalConversations();
          renderHistoryList(conversations);
          chatStream.scrollTop = chatStream.scrollHeight;
        },
        onError: (err) => {
          if (qaLoading) qaLoading.classList.add('hidden');
          if (qaSubmitBtn) qaSubmitBtn.disabled = false;
          if (cursorEl) cursorEl.remove();

          if (!hasReceivedTokens) {
            assistantMsg.remove();
            appendErrorMessage(err.message || 'LLM server connection error');
          } else {
            showToast(`Stream ended with error: ${err.message}`, 'error', 5000);
          }

          const msgLower = (err.message || '').toLowerCase();
          if (msgLower.includes('503') || msgLower.includes('connection') || msgLower.includes('refused')) {
            showToast('LLM service is unreachable. Please verify Ollama is running (`ollama serve`).', 'error', 6000);
          } else if (msgLower.includes('timeout')) {
            showToast('Model query timed out. Please try a more specific question.', 'error', 6000);
          } else {
            showToast(`Query failed: ${err.message}`, 'error', 5000);
          }
        }
      });
    } catch (err) {
      if (qaLoading) qaLoading.classList.add('hidden');
      if (qaSubmitBtn) qaSubmitBtn.disabled = false;
      if (cursorEl) cursorEl.remove();
      if (!hasReceivedTokens) {
        assistantMsg.remove();
        appendErrorMessage(err.message);
      }
      showToast(`Query failed: ${err.message}`, 'error', 5000);
    }
  }

  function renderUserBubble(text) {
    if (!chatStream) return;
    const msg = document.createElement('div');
    msg.className = 'chat-msg chat-msg--user';
    msg.innerHTML = `
      <div class="chat-avatar" title="You">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </div>
      <div class="chat-bubble">
        <div class="chat-sender">Engineering Query</div>
        <div class="chat-text"><p>${escapeHtml(text)}</p></div>
      </div>
    `;
    chatStream.appendChild(msg);
    chatStream.scrollTop = chatStream.scrollHeight;
  }

  function renderAssistantBubble(rawAnswer, model, citations) {
    if (!chatStream) return;

    const isNotFound = /this information was not found in the selected document|not found in the selected document|no information regarding|not specified in the selected document/i.test(rawAnswer);
    const citationsHtml = buildCitationsHtml(citations, isNotFound);

    const assistantMsg = document.createElement('div');
    assistantMsg.className = 'chat-msg chat-msg--assistant';
    assistantMsg.innerHTML = `
      <div class="chat-avatar" title="${escapeHtml(model || 'Local LLM')}">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/></svg>
      </div>
      <div class="chat-bubble">
        <div class="card-header-flex" style="margin-bottom: 8px;">
          <div class="chat-sender">AutoHLD Engineering Assistant · <span style="color:var(--text-muted); font-weight:normal;">${escapeHtml(model || 'Local LLM')}</span></div>
          <button class="btn btn-ghost btn-sm" onclick="navigator.clipboard.writeText(${JSON.stringify(rawAnswer)}); showToast('Answer copied', 'info');">Copy Answer</button>
        </div>

        ${isNotFound ? `
          <div class="grounding-notice">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div><strong>Specification Scope Notice:</strong> The requested technical detail was not found in the currently selected document.</div>
          </div>
        ` : ''}

        <div class="chat-text">
          ${formatAnswer(rawAnswer)}
        </div>

        <div class="sources-section" style="margin-top: 14px; border-top: 1px solid var(--border-subtle); padding-top: 10px;">
          <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">
            ${(citations && citations.length > 0) ? `Verified Document Citations (${citations.length})` : 'Source Evidence'}
          </div>
          <div class="sources-grid">
            ${citationsHtml}
          </div>
        </div>
      </div>
    `;
    chatStream.appendChild(assistantMsg);
    chatStream.scrollTop = chatStream.scrollHeight;
  }

  function appendErrorMessage(errText) {
    if (!chatStream) return;
    const msg = document.createElement('div');
    msg.className = 'chat-msg chat-msg--assistant';
    msg.innerHTML = `
      <div class="chat-avatar" style="background: rgba(239, 68, 68, 0.16); color: var(--danger); border-color: var(--danger);">✕</div>
      <div class="chat-bubble" style="border-color: rgba(239, 68, 68, 0.35);">
        <div class="chat-sender" style="color: var(--danger);">Inference Error</div>
        <div class="chat-text"><p>Could not retrieve answer: ${escapeHtml(errText)}</p></div>
      </div>
    `;
    chatStream.appendChild(msg);
    chatStream.scrollTop = chatStream.scrollHeight;
  }

  /**
   * Parse LLM markdown-style text into safe HTML.
   */
  function formatAnswer(raw) {
    if (!raw) return '';

    const lines = raw.split('\n');
    let html = '';
    let inList = false;
    let inOrderedList = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.trim() === '') {
        if (inList)        { html += '</ul>'; inList = false; }
        if (inOrderedList) { html += '</ol>'; inOrderedList = false; }
        html += '<div class="answer-spacer"></div>';
        continue;
      }

      if (/^###\s+/.test(line)) {
        if (inList)        { html += '</ul>'; inList = false; }
        if (inOrderedList) { html += '</ol>'; inOrderedList = false; }
        html += `<h4 class="answer-h4">${inlineFormat(line.replace(/^###\s+/, ''))}</h4>`;
        continue;
      }

      if (/^##\s+/.test(line)) {
        if (inList)        { html += '</ul>'; inList = false; }
        if (inOrderedList) { html += '</ol>'; inOrderedList = false; }
        html += `<h3 class="answer-h3">${inlineFormat(line.replace(/^##\s+/, ''))}</h3>`;
        continue;
      }

      if (/^[\-\*]\s+/.test(line.trim())) {
        if (inOrderedList) { html += '</ol>'; inOrderedList = false; }
        if (!inList)       { html += '<ul class="answer-list">'; inList = true; }
        html += `<li>${inlineFormat(line.trim().replace(/^[\-\*]\s+/, ''))}</li>`;
        continue;
      }

      if (/^\d+\.\s+/.test(line.trim())) {
        if (inList)           { html += '</ul>'; inList = false; }
        if (!inOrderedList)   { html += '<ol class="answer-list answer-list--ordered">'; inOrderedList = true; }
        html += `<li>${inlineFormat(line.trim().replace(/^\d+\.\s+/, ''))}</li>`;
        continue;
      }

      if (inList)        { html += '</ul>'; inList = false; }
      if (inOrderedList) { html += '</ol>'; inOrderedList = false; }
      html += `<p class="answer-para">${inlineFormat(line)}</p>`;
    }

    if (inList)        html += '</ul>';
    if (inOrderedList) html += '</ol>';

    return html;
  }

  function inlineFormat(text) {
    let s = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    s = s.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

    // [Page N] badge formatting
    s = s.replace(/\[?(Pages?\s[\d,\s&amp;]+)\]?/gi,
      '<span class="inline-citation"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> $1</span>');

    return s;
  }

  function buildCitationsHtml(citations, isNotFound) {
    if (!citations || citations.length === 0) {
      if (isNotFound) {
        return `
          <div style="color: var(--text-muted); font-size: 12px; padding: 6px 0; font-style: italic;">
            No document pages cited because the requested topic is not present in the selected document.
          </div>
        `;
      }
      return `
        <div style="color: var(--text-muted); font-size: 12px; padding: 6px 0;">
          Based on general context across the uploaded document.
        </div>
      `;
    }

    return citations.map((c, i) => {
      const pageNum = c.page_num || c.page || '—';
      const sectionName = c.section ? escapeHtml(c.section) : 'Specification Chunk';
      const excerpt = escapeHtml(c.text || c.excerpt || '(No excerpt text available)');
      const excerptId = `citation-exp-${Date.now()}-${i}`;

      return `
        <div class="citation-card">
          <div class="citation-head">
            <span class="badge-page">Page ${pageNum}</span>
            <span class="citation-section-label">${sectionName}</span>
          </div>
          <div class="citation-excerpt" id="${excerptId}">${excerpt}</div>
          <button class="citation-toggle-btn" onclick="QueryModule.toggleExcerpt('${excerptId}', this)">
            <span>View full excerpt</span> ▾
          </button>
        </div>
      `;
    }).join('');
  }

  function toggleExcerpt(id, btn) {
    const el = document.getElementById(id);
    if (!el) return;
    const isExpanded = el.classList.toggle('expanded');
    if (isExpanded) {
      el.style.maxHeight = 'none';
      btn.innerHTML = '<span>Collapse excerpt</span> ▴';
    } else {
      el.style.maxHeight = '120px';
      btn.innerHTML = '<span>View full excerpt</span> ▾';
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function submitQuestionFromComponent(compId) {
    switchTab('qa');
    startNewChat();
    if (qaInput) {
      qaInput.value = `Describe the ${compId} Software Component, its ports, and its interactions with other components.`;
      setTimeout(() => submitQuestion(), 100);
    }
  }

  init();

  return {
    refresh,
    clearChat,
    startNewChat,
    clearAllConversations,
    toggleHistorySidebar,
    toggleExcerpt,
    submitQuestionFromComponent,
    filterHistory,
    loadConversation,
    deleteConversation,
  };
})();
