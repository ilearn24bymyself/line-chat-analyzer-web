let offset = 0;
const limit = 50;
let currentQuery = "";
let currentName = "";
let selectedChatIds = new Set(); // 多選聊天室 (空 = 全部)
let currentChatName = "所有聊天室";
let currentStockCode = "";
let stockOnly = 0;
let linkOnly = 0;
let isLoading = false;
let hasMore = true;

const resultsDiv = document.getElementById('results');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const chatroomList = document.getElementById('chatroomList');
const senderTags = document.getElementById('senderTags');
const stockTags = document.getElementById('stockTags');
const stockOnlyToggle = document.getElementById('stockOnlyToggle');
const linkOnlyToggle = document.getElementById('linkOnlyToggle');
const paginationTrigger = document.getElementById('pagination_trigger');

window.onload = async () => {
    await loadChats();
    await loadTopStocks();
    performSearch(true);
    setupInfiniteScroll();
    setupImport();
};

// ---- 聊天室清單（多選 checkbox 模式） ----
async function loadChats() {
    const res = await fetch('/api/chats');
    const data = await res.json();
    if (!data.ok) return;

    const allItem = `
        <div class="chatroom-item all-item ${selectedChatIds.size === 0 ? 'active' : ''}" 
             id="chat_all" onclick="selectAllChats(this)">
            <span>📋 全部聊天室</span>
        </div>`;

    const listHtml = data.items.map(chat => {
        const checked = selectedChatIds.has(chat.id) ? 'checked' : '';
        const isActive = selectedChatIds.has(chat.id) ? 'active' : '';
        return `
            <div class="chatroom-item ${isActive}" id="chat_${chat.id}">
                <label class="chat-check-label" onclick="event.stopPropagation()">
                    <input type="checkbox" ${checked}
                        onchange="toggleChatSelect(${chat.id}, this)"
                        id="chk_${chat.id}">
                    <span>${escapeHtml(chat.name)}</span>
                </label>
                <div class="meta">${chat.message_count.toLocaleString()} 筆 / ${chat.last_message_at || '無'}</div>
                <div class="chat-actions">
                    <button class="action-btn" title="改名" onclick="startRename(${chat.id}, '${chat.name.replace(/'/g, "\\'")}')">✎</button>
                    <button class="action-btn del" title="移除" onclick="confirmDelete(${chat.id}, '${chat.name.replace(/'/g, "\\'")}')">✕</button>
                </div>
            </div>`;
    }).join('');

    chatroomList.innerHTML = allItem + listHtml;
    updateSelectionInfo();
}

function toggleChatSelect(id, checkbox) {
    if (checkbox.checked) {
        selectedChatIds.add(id);
    } else {
        selectedChatIds.delete(id);
    }
    // 更新樣式
    const el = document.getElementById(`chat_${id}`);
    if (el) el.classList.toggle('active', checkbox.checked);
    const allItem = document.getElementById('chat_all');
    if (allItem) allItem.classList.toggle('active', selectedChatIds.size === 0);

    // 切換聊天室時清除特定發言者與股票過濾，避免舊條件影響新搜尋
    currentName = "";
    currentStockCode = "";

    updateSelectionInfo();
    performSearch(true);
}

function selectAllChats(el) {
    selectedChatIds.clear();
    // Uncheck all checkboxes
    document.querySelectorAll('[id^="chk_"]').forEach(cb => {
        cb.checked = false;
        const chatEl = document.getElementById(`chat_${cb.id.replace('chk_', '')}`);
        if (chatEl) chatEl.classList.remove('active');
    });
    el.classList.add('active');

    // 切換聊天室時清除特定發言者與股票過濾
    currentName = "";
    currentStockCode = "";

    updateSelectionInfo();
    performSearch(true);
}

function updateSelectionInfo() {
    if (selectedChatIds.size === 0) {
        currentChatName = "所有聊天室";
    } else if (selectedChatIds.size === 1) {
        const id = [...selectedChatIds][0];
        const el = document.getElementById(`chat_${id}`);
        const name = el ? el.querySelector('span').textContent.trim() : `聊天室 ${id}`;
        currentChatName = name;
    } else {
        currentChatName = `已選 ${selectedChatIds.size} 個聊天室`;
    }
}

// ---- 股票 / 發言者 ----
async function loadTopStocks() {
    const chatParam = [...selectedChatIds].join(',');
    const res = await fetch(`/api/stocks/top?chat_id=${chatParam}`);
    const data = await res.json();
    if (data.ok) {
        stockTags.innerHTML = data.items.map(s => `
            <span class="tag stock ${currentStockCode === s.stock_code ? 'active' : ''}"
                  onclick="filterByStock('${s.stock_code}')">
                ${s.stock_code} ${s.stock_name} (${s.count})
            </span>`).join('');
    }
}

async function loadStats() {
    const chatParam = [...selectedChatIds].join(',');
    const res = await fetch(`/api/stats?chat_id=${chatParam}`);
    const data = await res.json();
    if (data.ok) {
        document.getElementById('total_stats').innerText = `目前範圍：${data.total.toLocaleString()} 筆訊息`;
        senderTags.innerHTML = data.senders.map(s => `
            <span class="tag ${currentName === s.name ? 'active' : ''}"
                  onclick="filterByName('${s.name}', this)">
                ${escapeHtml(s.name)} (${s.count})
            </span>`).join('');
    }
}

// ---- 搜尋 ----
async function performSearch(reset = false) {
    if (isLoading) return;
    if (!hasMore && !reset) return;

    isLoading = true;
    if (reset) {
        offset = 0; hasMore = true;
        resultsDiv.innerHTML = '<div class="loading">正在搜尋中...</div>';
        currentQuery = searchInput.value.trim();
        document.getElementById('current_info').innerText = `範圍: ${currentChatName} | 關鍵字: ${currentQuery || '無'}`;
        loadStats(); loadTopStocks();
    }

    const chatParam = [...selectedChatIds].join(',');
    const params = new URLSearchParams({
        q: currentQuery, name: currentName,
        chat_id: chatParam,
        stock_code: currentStockCode, has_stock: stockOnly, has_link: linkOnly,
        limit: limit, offset: offset
    });

    try {
        const res = await fetch(`/api/search?${params.toString()}`);
        const data = await res.json();
        if (reset && (!data.items || data.items.length === 0)) {
            resultsDiv.innerHTML = '<div class="empty">找不到符合條件的訊息</div>';
            hasMore = false;
        } else {
            if (reset) resultsDiv.innerHTML = '';
            if (data.items.length < limit) hasMore = false;
            renderItems(data.items);
            offset += limit;
        }
    } catch (e) {
        resultsDiv.innerHTML = '<div class="loading" style="color:red">API 服務異常</div>';
    } finally {
        isLoading = false;
    }
}

function renderItems(items) {
    const fragment = document.createDocumentFragment();
    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'msg-card';
        let msg = escapeHtml(item.message);
        msg = msg.replace(/https?:\/\/[^\s]+/g, url => `<a href="${url}" target="_blank">${url}</a>`);
        if (currentQuery) {
            const regex = new RegExp(`(${escapeRegExp(currentQuery)})`, 'gi');
            msg = msg.replace(regex, '<span class="highlight">$1</span>');
        }
        const showChatBadge = selectedChatIds.size !== 1;
        card.innerHTML = `
            ${showChatBadge ? `<div class="msg-from">📍 ${escapeHtml(item.chat_name)}</div>` : ''}
            <div class="msg-header"><span class="msg-name">${escapeHtml(item.name)}</span><span>${item.date} ${item.time}</span></div>
            <div class="msg-tags">
                ${item.has_stock_code ? `<span class="stock-tag">含股票代號</span>` : ''}
                ${item.has_link ? `<span class="link-tag">含網頁連結</span>` : ''}
            </div>
            <div class="msg-body">${msg}</div>
        `;
        card.onclick = () => copyToClipboard(item.message);
        fragment.appendChild(card);
    });
    resultsDiv.appendChild(fragment);
}

// ---- 篩選器 ----
function filterByName(name, el) {
    if (currentName === name) { currentName = ""; el.classList.remove('active'); }
    else { document.querySelectorAll('.tag').forEach(t => t.classList.remove('active')); currentName = name; el.classList.add('active'); }
    performSearch(true);
}

function filterByStock(code) {
    currentStockCode = currentStockCode === code ? "" : code;
    performSearch(true);
}

stockOnlyToggle.onchange = (e) => { stockOnly = e.target.checked ? 1 : 0; performSearch(true); };
linkOnlyToggle.onchange = (e) => { linkOnly = e.target.checked ? 1 : 0; performSearch(true); };

// ---- 刪除 / 改名 ----
function confirmDelete(id, name) {
    showModal("移除聊天室", `確定要移除「${name}」嗎？<br><br><span style="color:var(--danger)">警告：資料刪除後不可復原。</span>`);
    const footer = document.getElementById('modalActions'); footer.style.display = 'flex';
    const confirmBtn = document.getElementById('confirmBtn'); confirmBtn.style.display = 'block'; confirmBtn.innerText = "確認刪除";
    confirmBtn.onclick = async () => {
        confirmBtn.disabled = true;
        try {
            const res = await fetch(`/api/chats/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.ok) {
                closeModal();
                selectedChatIds.delete(id);
                loadChats(); performSearch(true);
            } else { alert(data.error); }
        } catch (e) { alert("刪除失敗"); } finally { confirmBtn.disabled = false; }
    };
}

function startRename(id, oldName) {
    const template = document.getElementById('renameTemplate');
    const content = template.content.cloneNode(true);
    const input = content.querySelector('#renameInput'); input.value = oldName;
    showModal("重新命名", "");
    const body = document.getElementById('modalBody'); body.innerHTML = ''; body.appendChild(content);
    document.getElementById('saveRenameBtn').onclick = async () => {
        const newName = document.getElementById('renameInput').value.trim();
        if (!newName) return;
        try {
            const res = await fetch(`/api/chats/${id}/rename`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newName }) });
            const data = await res.json();
            if (data.ok) { closeModal(); loadChats(); updateSelectionInfo(); }
            else { alert(data.error); }
        } catch (e) { alert("更新失敗"); }
    };
}

// ---- 匯入 ----
function setupImport() {
    const importBtn = document.getElementById('importBtn');
    const fileInput = document.getElementById('fileInput');
    importBtn.onclick = () => fileInput.click();
    fileInput.onchange = async () => {
        const file = fileInput.files[0]; if (!file) return;
        const template = document.getElementById('importOptionsTemplate');
        const content = template.content.cloneNode(true);
        showModal("匯入選項", "");
        const body = document.getElementById('modalBody'); body.innerHTML = ''; body.appendChild(content);
        document.getElementById('startImportBtn').onclick = async () => {
            const cleanup = document.getElementById('cleanupCheck').checked;
            const formData = new FormData();
            formData.append('file', file); formData.append('cleanup', cleanup);
            body.innerHTML = '<p class="loading">正在分析內容並進行去重處理...</p>';
            try {
                const res = await fetch('/api/import', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.ok) {
                    showModal("匯入成功", `聊天室：${data.chat_name}<br>新增：${data.inserted} 筆`, true);
                    await loadChats(); performSearch(true);
                } else { showModal("失敗", data.error, true); }
            } catch (e) { showModal("錯誤", "連線失敗", true); }
            fileInput.value = "";
        };
    };
}

// ---- 按鈕 ----
searchBtn.onclick = () => performSearch(true);
searchInput.onkeydown = (e) => { if (e.key === 'Enter') performSearch(true); };
document.getElementById('resetBtn').onclick = () => {
    currentQuery = ""; currentName = ""; currentStockCode = ""; stockOnly = 0; linkOnly = 0;
    searchInput.value = ""; stockOnlyToggle.checked = false; linkOnlyToggle.checked = false;
    performSearch(true);
};

// ---- 工具函式 ----
function setupInfiniteScroll() {
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoading) { performSearch(false); }
    }, { threshold: 0.1 });
    observer.observe(paginationTrigger);
}

function showModal(title, msg, simpleClose = false) {
    document.getElementById('overlay').style.display = 'flex';
    document.getElementById('modalTitle').innerText = title;
    document.getElementById('modalBody').innerHTML = msg ? `<p>${msg}</p>` : '';
    document.getElementById('modalActions').style.display = simpleClose ? 'flex' : 'none';
    document.getElementById('confirmBtn').style.display = 'none';
}
function closeModal() { document.getElementById('overlay').style.display = 'none'; }
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const toast = document.createElement('div');
        toast.style = "position:fixed; bottom:20px; right:20px; background:#21e6c1; color:#1a1a2e; padding:10px; border-radius:5px; z-index:999; font-weight:bold;";
        toast.innerText = "已複製訊息"; document.body.appendChild(toast); setTimeout(() => toast.remove(), 1000);
    });
}
function escapeHtml(text) { if (!text) return ""; const div = document.createElement('div'); div.textContent = text; return div.innerHTML; }
function escapeRegExp(string) { return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
