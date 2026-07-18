/* eslint-disable */
/**
 * Smart Assistant - Trợ Lý Mua Sắm Thông Thái
 * Giữ nguyên toàn bộ UI/UX (session sidebar, dark mode, mascot, thẻ sản
 * phẩm...) từ bản gốc, nhưng thay "bộ não" (trước đây là NLP heuristic +
 * MOCK_CATALOG cục bộ trong trình duyệt) bằng lời gọi API thật tới backend
 * Python (4 module: Slot-filling -> Retrieval/Filter -> Ranking ->
 * Explanation+Guardrail). Mọi số liệu hiển thị (giá, thông số, lý do chọn)
 * đều lấy trực tiếp từ response của backend — frontend không tự bịa/suy
 * diễn bất kỳ số liệu sản phẩm nào.
 */

const API_BASE = ''; // same-origin: frontend được FastAPI serve cùng cổng với API

const MOCK_FAQ = {
  'bảo hành': 'Dạ, sản phẩm tại Điện Máy Xanh được bảo hành chính hãng 1 đổi 1 trong vòng 30 ngày đầu nếu có lỗi phần cứng từ nhà sản xuất ạ!',
  'giao hàng': 'Dạ, hệ thống miễn phí vận chuyển lắp đặt trong bán kính 10km quanh siêu thị gần nhất ngay trong ngày ạ.',
  'trả góp': 'Dạ, hiện tại có chương trình hỗ trợ trả góp 0% lãi suất qua căn cước công dân gắn chip cực nhanh chóng, xét duyệt chỉ 5 phút ạ.',
};

let consumerChatSessions = [];
let activeSessionId = null;

// ==========================================
// SIDEBAR / DARK-MODE HELPERS (giữ nguyên từ bản gốc)
// ==========================================
function initCollapsibleSidebarLogic() {
  const sidebarPanel = document.getElementById('sidebar-panel');
  const btnClose = document.getElementById('btn-close-sidebar');
  const btnOpen = document.getElementById('btn-open-sidebar');
  if (!sidebarPanel || !btnClose || !btnOpen) return;

  btnClose.addEventListener('click', () => {
    sidebarPanel.classList.remove('w-80', 'p-5', 'border-r');
    sidebarPanel.classList.add('w-0', 'p-0', 'border-r-0', 'opacity-0', 'pointer-events-none');
    btnOpen.classList.remove('hidden');
  });
  btnOpen.addEventListener('click', () => {
    sidebarPanel.classList.remove('w-0', 'p-0', 'border-r-0', 'opacity-0', 'pointer-events-none');
    sidebarPanel.classList.add('w-80', 'p-5', 'border-r');
    btnOpen.classList.add('hidden');
  });
}

function injectJiggleStyles() {
  if (document.getElementById('mascot-jiggle-style')) return;
  const style = document.createElement('style');
  style.id = 'mascot-jiggle-style';
  style.innerHTML = `
    @keyframes jiggleVivid {
      0% { transform: scale(1) rotate(0deg); }
      15% { transform: scale(1.15) rotate(-10deg); }
      30% { transform: scale(1.15) rotate(8deg); }
      45% { transform: scale(1.08) rotate(-6deg); }
      60% { transform: scale(1.08) rotate(4deg); }
      75% { transform: scale(1.02) rotate(-2deg); }
      100% { transform: scale(1) rotate(0deg); }
    }
    .animate-jiggle-vivid { animation: jiggleVivid 0.6s ease-in-out; display: inline-block !important; }
  `;
  document.head.appendChild(style);
}

function triggerMascotJiggle() {
  document.querySelectorAll('img[src*="mascot"]').forEach((m) => {
    m.classList.add('animate-jiggle-vivid');
    setTimeout(() => m.classList.remove('animate-jiggle-vivid'), 600);
  });
}

// ==========================================
// UTILITIES & CHAT UI RENDERERS
// ==========================================
function formatVND(amount) {
  if (amount == null) return 'Chưa có dữ liệu giá';
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount).replace('₫', 'đ');
}

function scrollChatToBottom() {
  const chatBox = document.getElementById('chat-box');
  if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
}

function showTypingIndicator() {
  const chatBox = document.getElementById('chat-box');
  if (!chatBox) return;
  const html = `
    <div id="typing-indicator" class="flex items-start space-x-3.5 message-fade-in">
      <div class="w-10 h-10 rounded-xl bg-white border border-slate-200 dark:border-brand-border flex items-center justify-center overflow-hidden shrink-0 shadow-md">
        <img src="img/mascot.png" alt="..." class="w-full h-full object-contain p-0.5 animate-pulse" onerror="this.src='https://placehold.co/100x100?text=Mascot'">
      </div>
      <div class="glass-message-card text-slate-400 rounded-2xl rounded-tl-none px-4 py-3 border border-slate-200 dark:border-brand-border">
        <div class="flex items-center space-x-1 py-1">
          <span class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></span>
          <span class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></span>
          <span class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></span>
        </div>
      </div>
    </div>`;
  chatBox.insertAdjacentHTML('beforeend', html);
  scrollChatToBottom();
}

function removeTypingIndicator() {
  const indicator = document.getElementById('typing-indicator');
  if (indicator) indicator.remove();
}

function appendUserMessage(text) {
  const chatBox = document.getElementById('chat-box');
  if (!chatBox) return;
  const html = `
    <div class="flex items-start space-x-3 justify-end message-fade-in">
      <div class="space-y-1 max-w-[80%]">
        <div class="bg-gradient-to-r from-[#1d4ed8] to-[#0095da] text-white rounded-2xl rounded-tr-none px-4 py-3 shadow-md">
          <p class="text-sm leading-relaxed">${escapeHtml(text)}</p>
        </div>
      </div>
      <div class="w-9 h-9 rounded-xl bg-white dark:bg-brand-panel border border-slate-200 dark:border-brand-border flex items-center justify-center shrink-0 shadow-sm">
        <i class="fa-solid fa-user text-brand-electric text-sm"></i>
      </div>
    </div>`;
  chatBox.insertAdjacentHTML('beforeend', html);
  scrollChatToBottom();

  if (activeSessionId) {
    const s = consumerChatSessions.find((item) => item.id === activeSessionId);
    if (s) s.messages.push({ role: 'user', content: escapeHtml(text) });
  }
}

function appendAssistantMessage(htmlContent) {
  const chatBox = document.getElementById('chat-box');
  if (!chatBox) return;
  const html = `
    <div class="flex items-start space-x-3.5 message-fade-in">
      <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-white to-slate-100 border border-white flex items-center justify-center shrink-0 shadow-[0_4px_10px_rgba(0,149,218,0.15)] overflow-hidden">
        <img src="img/mascot.png" alt="Avatar" class="w-[85%] h-[85%] object-contain" onerror="this.src='https://placehold.co/100x100?text=AI'">
      </div>
      <div class="space-y-1 max-w-[85%] w-full">
        <div class="glass-message-card text-slate-800 dark:text-slate-200 rounded-2xl rounded-tl-none px-5 py-3.5 border border-white/50 dark:border-brand-border/40">
          ${htmlContent}
        </div>
      </div>
    </div>`;
  chatBox.insertAdjacentHTML('beforeend', html);
  scrollChatToBottom();

  if (activeSessionId) {
    const s = consumerChatSessions.find((item) => item.id === activeSessionId);
    if (s) s.messages.push({ role: 'assistant', content: htmlContent });
  }
}
window.appendAssistantMessage = appendAssistantMessage;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ==========================================
// QUẢN LÝ LỊCH SỬ PHIÊN TRÒ CHUYỆN (SESSIONS)
// session.id ĐƯỢC DÙNG LUÔN LÀM session_id gửi cho backend — backend giữ
// state hội thoại (slot đã hỏi, category, ranking...) theo đúng id này.
// ==========================================
function createNewChatSession(initialTitle = 'Cuộc trò chuyện mới') {
  const newId = 'session_' + Date.now();
  const newSession = {
    id: newId,
    title: initialTitle,
    timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
    messages: [],
    category: null,
  };
  consumerChatSessions.unshift(newSession);
  activeSessionId = newId;
  renderChatHistoryUI();
  return newSession;
}

function updateActiveSessionTitle(newTitle, categoryCode) {
  if (!activeSessionId) return;
  const s = consumerChatSessions.find((item) => item.id === activeSessionId);
  if (s) {
    s.title = newTitle;
    if (categoryCode) s.category = categoryCode;
    renderChatHistoryUI();
  }
}

function renderChatHistoryUI() {
  const container = document.getElementById('chat-history-list');
  if (!container) return;

  if (consumerChatSessions.length === 0) {
    container.innerHTML = `
      <div id="history-empty-state" class="text-center py-8 px-4 border border-dashed border-slate-200 dark:border-brand-border/40 rounded-xl">
        <p class="text-[11px] text-slate-400 italic">Chưa có cuộc trò chuyện cũ.</p>
      </div>`;
    return;
  }

  container.innerHTML = '';
  consumerChatSessions.forEach((session) => {
    const isActive = session.id === activeSessionId;
    const pill = document.createElement('div');
    pill.className = `group flex items-center justify-between p-3 rounded-xl border transition-all duration-200 cursor-pointer text-xs font-medium history-item-appear ${
      isActive
        ? 'border-brand-electric/40 bg-brand-electric/5 text-brand-electric dark:bg-brand-electric/10'
        : 'border-slate-100 dark:border-brand-border/40 bg-slate-50/60 dark:bg-brand-panel/40 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-brand-dark/30'
    }`;

    let icon = '<i class="fa-regular fa-comment text-slate-400"></i>';
    if (session.category === 'air_conditioner') icon = '<i class="fa-solid fa-snowflake text-cyan-500"></i>';
    if (session.category && session.category.includes('tu_lanh')) icon = '<i class="fa-solid fa-carrot text-emerald-500"></i>';
    if (session.category === 'laptop') icon = '<i class="fa-solid fa-laptop text-indigo-500"></i>';

    pill.innerHTML = `
      <div class="flex items-center space-x-2.5 truncate w-[90%]">
        <span class="shrink-0 text-sm">${icon}</span>
        <div class="truncate flex flex-col text-left">
          <span class="truncate font-semibold text-slate-900 dark:text-slate-100">${escapeHtml(session.title)}</span>
          <span class="text-[10px] text-slate-400 mt-0.5">${session.timestamp} • Điện Máy Xanh</span>
        </div>
      </div>`;
    pill.addEventListener('click', () => {
      activeSessionId = session.id;
      renderChatHistoryUI();
      restoreSessionMessages(session);
    });
    container.appendChild(pill);
  });
}

function restoreSessionMessages(session) {
  const chatBox = document.getElementById('chat-box');
  if (!chatBox) return;

  if (!session.messages || session.messages.length === 0) {
    chatBox.innerHTML = `
      <div class="flex items-start space-x-3.5 message-fade-in">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-white to-slate-100 border border-white flex items-center justify-center overflow-hidden shrink-0 shadow-[0_4px_10px_rgba(0,149,218,0.15)] bg-white">
          <img src="img/mascot.png" alt="Avatar" class="w-[85%] h-[85%] object-contain" onerror="this.src='https://placehold.co/100x100?text=AI'">
        </div>
        <div class="space-y-1 max-w-[85%] w-full">
          <div class="glass-message-card text-slate-800 dark:text-slate-200 rounded-2xl rounded-tl-none px-5 py-3.5 border border-white/50 dark:border-brand-border/40">
            <p class="text-sm">Dạ, phiên hội thoại tư vấn mua sắm mới đã sẵn sàng phục vụ rồi ạ!</p>
          </div>
        </div>
      </div>`;
    updateDebugPanel({ status: 'INIT' });
    scrollChatToBottom();
    return;
  }

  chatBox.innerHTML = '';
  session.messages.forEach((msg) => {
    if (msg.role === 'user') {
      chatBox.insertAdjacentHTML(
        'beforeend',
        `<div class="flex items-start space-x-3 justify-end message-fade-in"><div class="max-w-[80%] bg-gradient-to-r from-[#1d4ed8] to-[#0095da] text-white rounded-2xl rounded-tr-none px-4 py-3 text-[13.5px] shadow-sm">${msg.content}</div></div>`
      );
    } else {
      chatBox.insertAdjacentHTML(
        'beforeend',
        `<div class="flex items-start space-x-3.5 message-fade-in"><div class="w-10 h-10 rounded-xl bg-white border border-white flex items-center justify-center shrink-0 shadow-[0_4px_10px_rgba(0,149,218,0.15)] overflow-hidden"><img src="img/mascot.png" class="w-[85%] h-[85%] object-contain"></div><div class="max-w-[85%] w-full glass-message-card text-slate-800 dark:text-slate-200 rounded-2xl rounded-tl-none px-5 py-3.5 text-[13.5px]">${msg.content}</div></div>`
      );
    }
  });

  document.getElementById('active-category').textContent = session.category || 'Chưa xác định';
  scrollChatToBottom();
}

// ==========================================
// GỌI BACKEND THẬT (thay cho MOCK_CATALOG + NLP heuristic cục bộ)
// ==========================================
async function sendMessageToBackend(sessionId, message) {
  // Lấy state đã lưu trong localStorage (nếu có) để gửi kèm — cho phép
  // backend khôi phục session nếu vừa restart. Backward compatible:
  // backend cũ không có field state vẫn bỏ qua.
  let clientState = null;
  try {
    const raw = localStorage.getItem(`session_state_${sessionId}`);
    if (raw) clientState = JSON.parse(raw);
  } catch (_) {}

  const body = { session_id: sessionId, message };
  if (clientState) body.state = clientState;

  const res = await fetch(`${API_BASE}/api/conversation/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Lỗi API (${res.status})`);
  }
  const data = await res.json();
  // Lưu state mới nhất vào localStorage để backend có thể khôi phục
  if (data.state && sessionId) {
    try {
      localStorage.setItem(`session_state_${sessionId}`, JSON.stringify(data.state));
    } catch (_) {}
  }
  return data;
}

function updateDebugPanel(data) {
  const state = data.state || {};
  document.getElementById('active-category').textContent = state.category || 'Chưa xác định';
  document.getElementById('chat-stage').textContent = data.status || 'INIT';
  document.getElementById('slang-inspector').textContent = state.slots ? JSON.stringify(state.slots) : '';

  if (data.status === 'ok' || data.status === 'corrected' || data.status === 'blocked') {
    const meta = data.ranking_meta || {};
    document.getElementById('rag-catalog-status').textContent = `Tìm thấy ${meta.total_scored || 0} sản phẩm phù hợp`;
    document.getElementById('rag-promo-status').textContent =
      meta.relaxed_steps && meta.relaxed_steps.length ? `Đã nới: ${meta.relaxed_steps.join(', ')}` : 'Khớp đúng yêu cầu';
  } else {
    document.getElementById('rag-catalog-status').textContent = '';
    document.getElementById('rag-promo-status').textContent = '';
  }
}

function dmxProductLink(item) {
  if (item.url) return item.url;
  const q = encodeURIComponent(item.name || item.model_code || item.product_id || '');
  return `https://www.dienmayxanh.com/tim-kiem?key=${q}`;
}

function renderProductCards(data) {
  const items = data.items || [];
  const summaryText = data.summary || 'Dưới đây là các sản phẩm phù hợp nhất với nhu cầu của bạn:';

  let html = `<p class="text-[13.5px] leading-relaxed mb-4 text-slate-800 dark:text-slate-200">${escapeHtml(summaryText)}</p>`;

  if (data.status === 'corrected' && data.corrections && data.corrections.length > 0) {
    html += `<p class="text-[11px] text-amber-600 dark:text-amber-400 mb-3 flex items-center"><i class="fa-solid fa-shield-halved mr-1.5"></i>${data.corrections.length} thông tin đã được hệ thống kiểm tra và tự động sửa để đảm bảo chính xác.</p>`;
  }

  html += `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">`;

  items.forEach((item, idx) => {
    const missingNote = item.llm_explanation_missing
      ? `<p class="text-[11px] text-slate-400 italic mt-2">Chưa có mô tả chi tiết từ AI cho sản phẩm này — chỉ hiển thị dữ liệu gốc từ hệ thống.</p>`
      : '';
    const pros = (item.pros || []).map((p) => `<li><i class="fa-solid fa-check text-emerald-500 mr-1.5"></i>${escapeHtml(p)}</li>`).join('');
    const cons = (item.cons || []).map((c) => `<li><i class="fa-solid fa-triangle-exclamation text-amber-500 mr-1.5"></i>${escapeHtml(c)}</li>`).join('');
    // Tên sản phẩm THẬT luôn hiển thị (kể cả khi chưa qua AI) — headline
    // (do AI sinh ra, có thể vắng mặt khi fallback) chỉ là phụ đề bổ sung.
    const productName = item.name || item.headline || 'Sản phẩm phù hợp';
    const headlineSubtitle = item.headline && item.headline !== productName ? `<p class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">${escapeHtml(item.headline)}</p>` : '';
    const imageHtml = item.image
      ? `<img src="${escapeHtml(item.image)}" alt="${escapeHtml(productName)}" class="w-full h-28 object-contain rounded-lg bg-slate-50 dark:bg-brand-dark/40 mb-2" onerror="this.style.display='none'">`
      : '';

    html += `
      <div class="bg-white dark:bg-brand-panel/90 rounded-xl p-4 border border-slate-200 dark:border-brand-border flex flex-col justify-between space-y-3.5 shadow-sm transition-all hover:shadow-md hover:border-brand-electric/40">
        <div>
          <div class="flex items-center justify-between">
            <span class="px-2 py-0.5 text-[10px] font-bold bg-brand-electric/10 text-brand-electric rounded">Đề xuất ${idx + 1}</span>
            <span class="px-2 py-0.5 text-[9px] font-mono text-slate-400" title="Mã sản phẩm nguồn">#${escapeHtml(item.product_id || '')}</span>
          </div>
          ${imageHtml}
          <h3 class="font-bold text-[12.5px] text-slate-900 dark:text-white mt-2 line-clamp-2 leading-snug">${escapeHtml(productName)}</h3>
          ${headlineSubtitle}
          <div class="text-[15px] font-extrabold text-blue-600 dark:text-brand-electric mt-1.5">${formatVND(item.effective_price)}</div>

          ${pros ? `<ul class="text-[11px] text-slate-600 dark:text-slate-400 mt-2.5 space-y-1 bg-slate-50 dark:bg-brand-dark/40 p-2.5 rounded-lg border border-slate-100 dark:border-brand-border/30">${pros}</ul>` : ''}
          ${missingNote}
        </div>

        ${
          cons
            ? `<div class="bg-amber-500/5 dark:bg-amber-500/10 p-2.5 rounded-lg text-[11px] text-amber-800 dark:text-amber-400 border border-amber-500/20 leading-relaxed">
                 <strong>Điểm đánh đổi (Trade-off):</strong><ul class="mt-1 space-y-1">${cons}</ul>
               </div>`
            : ''
        }

        <a href="${dmxProductLink(item)}" target="_blank" rel="noopener noreferrer"
           class="w-full custom-btn-select text-xs py-2.5 rounded-xl font-bold transition-all shadow-sm flex items-center justify-center gap-1.5">
          <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>Xem tại Điện Máy Xanh
        </a>
      </div>`;
  });

  html += `</div>`;
  return html;
}

function renderResponse(data) {
  updateDebugPanel(data);

  switch (data.status) {
    case 'need_clarification':
    case 'not_ready':
      appendAssistantMessage(`<p class="text-sm">${escapeHtml(data.reply)}</p>`);
      break;
    case 'no_results':
      appendAssistantMessage(
        `<p class="text-sm"><i class="fa-solid fa-circle-info text-brand-electric mr-1.5"></i>${escapeHtml(data.reply)}</p>`
      );
      break;
    case 'llm_error':
    case 'llm_parse_error':
      appendAssistantMessage(
        `<p class="text-sm text-amber-600 dark:text-amber-400"><i class="fa-solid fa-triangle-exclamation mr-1.5"></i>${escapeHtml(data.reply)}</p>`
      );
      break;
    case 'blocked':
      appendAssistantMessage(
        `<p class="text-sm text-amber-600 dark:text-amber-400"><i class="fa-solid fa-shield-halved mr-1.5"></i>${escapeHtml(data.reply)}</p>`
      );
      break;
    case 'ok':
    case 'corrected':
      appendAssistantMessage(renderProductCards(data));
      if (data.state && data.state.category) {
        updateActiveSessionTitle(`Tư vấn: ${data.state.category}`, data.state.category);
      }
      break;
    default:
      appendAssistantMessage(`<p class="text-sm">${escapeHtml(data.reply || 'Đã nhận được phản hồi từ hệ thống.')}</p>`);
  }
}

// ==========================================
// ĐIỀU PHỐI GỬI TIN NHẮN
// ==========================================
function handleFormSubmit(event) {
  event.preventDefault();
  const input = document.getElementById('user-input');
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;

  if (!activeSessionId) createNewChatSession();

  appendUserMessage(val);
  input.value = '';
  showTypingIndicator();

  const startTime = performance.now();

  // FAQ tra nhanh cục bộ (bảo hành/giao hàng/trả góp) — không cần gọi backend
  const lower = val.toLowerCase();
  for (const [key, answer] of Object.entries(MOCK_FAQ)) {
    if (lower.includes(key)) {
      removeTypingIndicator();
      document.getElementById('rag-faq-status').textContent = `Khớp FAQ: [${key}]`;
      document.getElementById('latency-val').textContent = Math.round(performance.now() - startTime) + 'ms';
      appendAssistantMessage(`<p class="text-sm"><i class="fa-solid fa-circle-info text-brand-electric mr-1.5"></i>${answer}</p>`);
      return;
    }
  }
  document.getElementById('rag-faq-status').textContent = 'Không khớp FAQ';

  sendMessageToBackend(activeSessionId, val)
    .then((data) => {
      removeTypingIndicator();
      document.getElementById('latency-val').textContent = Math.round(performance.now() - startTime) + 'ms';
      renderResponse(data);
    })
    .catch((err) => {
      removeTypingIndicator();
      document.getElementById('latency-val').textContent = Math.round(performance.now() - startTime) + 'ms';
      appendAssistantMessage(
        `<p class="text-sm text-red-500"><i class="fa-solid fa-circle-exclamation mr-1.5"></i>Không kết nối được tới hệ thống tư vấn (${escapeHtml(
          err.message
        )}). Vui lòng thử lại sau.</p>`
      );
    });
}

// ==========================================
// RESET / QUICK PROMPT
// ==========================================
window.resetConversation = function () {
  if (activeSessionId) {
    const currentSession = consumerChatSessions.find((item) => item.id === activeSessionId);
    if (currentSession && (!currentSession.messages || currentSession.messages.length === 0)) {
      return;
    }
    // Đồng bộ reset với backend để state hội thoại (slot đã hỏi, category...) không lệch với UI
    fetch(`${API_BASE}/api/conversation/${activeSessionId}/reset`, { method: 'POST' }).catch(() => {});
  }

  const chatBox = document.getElementById('chat-box');
  if (chatBox) {
    chatBox.innerHTML = `
      <div class="flex items-start space-x-3.5 message-fade-in">
        <div class="w-10 h-10 rounded-xl bg-white border border-white flex items-center justify-center overflow-hidden shrink-0 shadow-[0_4px_10px_rgba(0,149,218,0.15)]">
          <img src="img/mascot.png" alt="Avatar" class="w-[85%] h-[85%] object-contain" onerror="this.src='https://placehold.co/100x100?text=AI'">
        </div>
        <div class="space-y-1 max-w-[85%] w-full">
          <div class="glass-message-card text-slate-800 dark:text-slate-200 rounded-2xl rounded-tl-none px-5 py-3.5 border border-white/50 dark:border-brand-border/40">
            <p class="text-sm">Dạ, phiên hội thoại tư vấn mua sắm mới đã sẵn sàng phục vụ rồi ạ! Anh/chị cần em hỗ trợ tìm kiếm dòng thiết bị công nghệ điện máy nào thế ạ?</p>
          </div>
        </div>
      </div>`;
  }

  document.getElementById('active-category').textContent = 'Chưa xác định';
  document.getElementById('chat-stage').textContent = 'INIT';
  document.getElementById('slang-inspector').textContent = '';
  document.getElementById('rag-catalog-status').textContent = '';
  document.getElementById('rag-promo-status').textContent = '';
  document.getElementById('rag-faq-status').textContent = '';

  createNewChatSession();
};

// ==========================================
// CATEGORIES ĐỘNG — gọi /api/categories
// ==========================================
let _allCategories = [];
let _categoriesExpanded = false;
const POPULAR_LIMIT = 6;

async function loadCategories() {
  try {
    const res = await fetch(`${API_BASE}/api/categories`);
    if (!res.ok) return;
    const data = await res.json();
    _allCategories = data.categories || [];
    renderCategoryButtons();
  } catch (_) {
    // Không critical — UI vẫn hoạt động với nút hardcode trong welcome message
  }
}

function renderCategoryButtons() {
  const container = document.getElementById('quick-category-buttons');
  if (!container || !_allCategories.length) return;

  const popular = _allCategories.filter((c) => c.popular);
  const others = _allCategories.filter((c) => !c.popular);
  const toShow = _categoriesExpanded ? _allCategories : popular.slice(0, POPULAR_LIMIT);

  container.innerHTML = '';

  toShow.forEach((cat) => {
    const btn = document.createElement('span');
    btn.className = 'px-3 py-1 bg-[#fffbf4] hover:bg-[#fff3db] text-[#b25e00] text-xs font-semibold rounded-lg border border-[#f5d0a1] cursor-pointer transition-all duration-150 shadow-sm active:scale-95';
    btn.textContent = cat.name;
    btn.addEventListener('click', () => window.fillQuickPrompt(cat.prompt));
    container.appendChild(btn);
  });

  // Nút "Xem thêm" / "Thu gọn"
  if (!_categoriesExpanded && others.length > 0) {
    const moreBtn = document.createElement('span');
    moreBtn.className = 'px-3 py-1 bg-brand-electric/10 hover:bg-brand-electric/20 text-brand-electric text-xs font-semibold rounded-lg border border-brand-electric/20 cursor-pointer transition-all duration-150 shadow-sm active:scale-95';
    moreBtn.textContent = `+${others.length} ngành khác`;
    moreBtn.addEventListener('click', () => { _categoriesExpanded = true; renderCategoryButtons(); });
    container.appendChild(moreBtn);
  } else if (_categoriesExpanded && _allCategories.length > POPULAR_LIMIT) {
    const collapseBtn = document.createElement('span');
    collapseBtn.className = 'px-3 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-brand-panel dark:hover:bg-brand-border text-slate-600 dark:text-slate-300 text-xs font-semibold rounded-lg border border-slate-200 dark:border-brand-border cursor-pointer transition-all duration-150 shadow-sm active:scale-95';
    collapseBtn.textContent = 'Thu gọn';
    collapseBtn.addEventListener('click', () => { _categoriesExpanded = false; renderCategoryButtons(); });
    container.appendChild(collapseBtn);
  }
}

window.fillQuickPrompt = function (promptText) {
  const input = document.getElementById('user-input');
  if (input) {
    input.value = promptText;
    input.focus();
  }
};

// ==========================================
// KHỞI TẠO KHI TẢI TRANG
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('chat-form');
  if (form) form.addEventListener('submit', handleFormSubmit);

  initCollapsibleSidebarLogic();
  injectJiggleStyles();

  createNewChatSession();

  // Tải danh sách ngành từ backend — không chặn UI
  loadCategories();
});
