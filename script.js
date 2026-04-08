// === State ===
const editor = document.getElementById('editor');
const docTitle = document.getElementById('doc-title');
const saveStatus = document.getElementById('save-status');
let currentDocId = null;
let autoSaveTimer = null;
let isDirty = false;

const STORAGE_KEY = 'wp_documents';

// === Document Management ===
function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function getAllDocuments() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
        return {};
    }
}

function saveDocument() {
    const docs = getAllDocuments();
    if (!currentDocId) {
        currentDocId = generateId();
    }
    docs[currentDocId] = {
        title: docTitle.value || 'Untitled Document',
        content: editor.innerHTML,
        savedAt: new Date().toISOString()
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(docs));
    isDirty = false;
    updateSaveStatus('All changes saved');
}

function autoSave() {
    if (isDirty) {
        saveDocument();
    }
}

function markDirty() {
    isDirty = true;
    updateSaveStatus('Unsaved changes');
    clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(autoSave, 2000);
}

function updateSaveStatus(text) {
    saveStatus.textContent = text;
}

function newDocument() {
    if (isDirty && !confirm('You have unsaved changes. Create a new document anyway?')) {
        return;
    }
    currentDocId = null;
    docTitle.value = 'Untitled Document';
    editor.innerHTML = '<p><br></p>';
    isDirty = false;
    updateSaveStatus('New document');
    editor.focus();
    closeAllMenus();
}

function openDocumentPicker() {
    closeAllMenus();
    const docs = getAllDocuments();
    const list = document.getElementById('saved-docs-list');
    const entries = Object.entries(docs);

    if (entries.length === 0) {
        list.innerHTML = '<p class="no-docs">No saved documents found.</p>';
    } else {
        list.innerHTML = entries.map(([id, doc]) => {
            const date = new Date(doc.savedAt).toLocaleString();
            return `
                <div class="saved-doc-item" onclick="loadDocument('${id}')">
                    <div class="saved-doc-info">
                        <div class="saved-doc-name">${escapeHtml(doc.title)}</div>
                        <div class="saved-doc-date">${date}</div>
                    </div>
                    <button class="saved-doc-delete" onclick="event.stopPropagation(); deleteDocument('${id}')" title="Delete">&times;</button>
                </div>
            `;
        }).join('');
    }

    showModal('open-modal');
}

function loadDocument(id) {
    const docs = getAllDocuments();
    const doc = docs[id];
    if (!doc) return;

    currentDocId = id;
    docTitle.value = doc.title;
    editor.innerHTML = doc.content;
    isDirty = false;
    updateSaveStatus('All changes saved');
    closeModal();
    editor.focus();
}

function deleteDocument(id) {
    if (!confirm('Delete this document?')) return;
    const docs = getAllDocuments();
    delete docs[id];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(docs));
    if (currentDocId === id) {
        currentDocId = null;
    }
    openDocumentPicker();
}

function saveAsNew() {
    closeAllMenus();
    document.getElementById('saveas-name').value = docTitle.value;
    showModal('saveas-modal');
    document.getElementById('saveas-name').focus();
}

function confirmSaveAs() {
    const name = document.getElementById('saveas-name').value.trim();
    if (!name) return;
    currentDocId = generateId();
    docTitle.value = name;
    saveDocument();
    closeModal();
}

// === Export ===
function exportHTML() {
    closeAllMenus();
    const title = docTitle.value || 'document';
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${escapeHtml(title)}</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }
        table { border-collapse: collapse; width: 100%; }
        td, th { border: 1px solid #ddd; padding: 8px; }
    </style>
</head>
<body>
${editor.innerHTML}
</body>
</html>`;
    downloadFile(title + '.html', html, 'text/html');
}

function exportText() {
    closeAllMenus();
    const title = docTitle.value || 'document';
    const text = editor.innerText;
    downloadFile(title + '.txt', text, 'text/plain');
}

function downloadFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function printDocument() {
    closeAllMenus();
    window.print();
}

// === Formatting Commands ===
function execCmd(command, value) {
    editor.focus();
    document.execCommand(command, false, value || null);
    updateToolbarState();
}

function changeFont(font) {
    editor.focus();
    document.execCommand('fontName', false, font);
}

function changeFontSize(size) {
    editor.focus();
    document.execCommand('fontSize', false, size);
}

function changeHeading(tag) {
    editor.focus();
    if (tag === 'p') {
        document.execCommand('formatBlock', false, '<p>');
    } else {
        document.execCommand('formatBlock', false, '<' + tag + '>');
    }
    document.getElementById('heading-select').value = tag;
}

function changeFontColor(color) {
    editor.focus();
    document.execCommand('foreColor', false, color);
    document.getElementById('text-color-indicator').style.background = color;
}

function changeHighlightColor(color) {
    editor.focus();
    document.execCommand('hiliteColor', false, color);
    document.getElementById('highlight-color-indicator').style.background = color;
}

function clearAllFormatting() {
    closeAllMenus();
    editor.focus();
    document.execCommand('removeFormat', false, null);
}

// === Insert ===
function insertLink() {
    closeAllMenus();
    const url = prompt('Enter URL:');
    if (url) {
        editor.focus();
        document.execCommand('createLink', false, url);
    }
}

function insertImage() {
    closeAllMenus();
    const url = prompt('Enter image URL:');
    if (url) {
        editor.focus();
        document.execCommand('insertImage', false, url);
    }
}

function insertHorizontalRule() {
    closeAllMenus();
    editor.focus();
    document.execCommand('insertHorizontalRule', false, null);
}

function insertTable() {
    closeAllMenus();
    document.getElementById('table-rows').value = 3;
    document.getElementById('table-cols').value = 3;
    showModal('table-modal');
}

function confirmInsertTable() {
    const rows = parseInt(document.getElementById('table-rows').value) || 3;
    const cols = parseInt(document.getElementById('table-cols').value) || 3;

    let html = '<table>';
    for (let r = 0; r < rows; r++) {
        html += '<tr>';
        for (let c = 0; c < cols; c++) {
            const tag = r === 0 ? 'th' : 'td';
            html += `<${tag}><br></${tag}>`;
        }
        html += '</tr>';
    }
    html += '</table><p><br></p>';

    editor.focus();
    document.execCommand('insertHTML', false, html);
    closeModal();
}

// === Toolbar State ===
function updateToolbarState() {
    const commands = {
        'btn-bold': 'bold',
        'btn-italic': 'italic',
        'btn-underline': 'underline',
        'btn-strikethrough': 'strikeThrough'
    };

    for (const [id, cmd] of Object.entries(commands)) {
        const el = document.getElementById(id);
        if (el) {
            el.classList.toggle('active', document.queryCommandState(cmd));
        }
    }

    const alignments = {
        'btn-align-left': 'justifyLeft',
        'btn-align-center': 'justifyCenter',
        'btn-align-right': 'justifyRight',
        'btn-align-justify': 'justifyFull'
    };

    for (const [id, cmd] of Object.entries(alignments)) {
        const el = document.getElementById(id);
        if (el) {
            el.classList.toggle('active', document.queryCommandState(cmd));
        }
    }

    // Update font family selector
    const fontName = document.queryCommandValue('fontName').replace(/['"]/g, '');
    const fontSelect = document.getElementById('font-family');
    for (const opt of fontSelect.options) {
        if (fontName.toLowerCase().includes(opt.value.toLowerCase())) {
            fontSelect.value = opt.value;
            break;
        }
    }

    // Update font size selector
    const fontSize = document.queryCommandValue('fontSize');
    if (fontSize) {
        document.getElementById('font-size').value = fontSize;
    }

    // Update heading selector
    const block = document.queryCommandValue('formatBlock');
    const headingSelect = document.getElementById('heading-select');
    const blockLower = block.toLowerCase();
    if (['h1', 'h2', 'h3', 'h4'].includes(blockLower)) {
        headingSelect.value = blockLower;
    } else {
        headingSelect.value = 'p';
    }
}

// === Word / Character Count ===
function updateCounts() {
    const text = editor.innerText || '';
    const trimmed = text.trim();

    const words = trimmed === '' ? 0 : trimmed.split(/\s+/).length;
    const chars = trimmed.length;
    const lines = text === '' ? 0 : text.split('\n').length;

    document.getElementById('word-count').textContent = `Words: ${words}`;
    document.getElementById('char-count').textContent = `Characters: ${chars}`;
    document.getElementById('line-count').textContent = `Lines: ${lines}`;
}

// === Find & Replace ===
let findMatches = [];
let findCurrentIndex = -1;

function toggleFindBar() {
    const bar = document.getElementById('find-bar');
    bar.classList.toggle('show');
    if (bar.classList.contains('show')) {
        document.getElementById('find-input').focus();
    } else {
        clearHighlights();
    }
}

function closeFindBar() {
    document.getElementById('find-bar').classList.remove('show');
    clearHighlights();
}

function clearHighlights() {
    // Remove existing highlights by replacing mark elements with their text
    const marks = editor.querySelectorAll('mark[data-find]');
    marks.forEach(mark => {
        const text = document.createTextNode(mark.textContent);
        mark.parentNode.replaceChild(text, mark);
    });
    editor.normalize();
    findMatches = [];
    findCurrentIndex = -1;
    document.getElementById('find-count').textContent = '';
}

function findInDocument() {
    clearHighlights();
    const query = document.getElementById('find-input').value;
    if (!query) return;

    const treeWalker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (treeWalker.nextNode()) {
        textNodes.push(treeWalker.currentNode);
    }

    const lowerQuery = query.toLowerCase();
    let count = 0;

    textNodes.forEach(node => {
        const text = node.textContent;
        const lowerText = text.toLowerCase();
        let idx = lowerText.indexOf(lowerQuery);
        if (idx === -1) return;

        const frag = document.createDocumentFragment();
        let lastIdx = 0;

        while (idx !== -1) {
            if (idx > lastIdx) {
                frag.appendChild(document.createTextNode(text.substring(lastIdx, idx)));
            }
            const mark = document.createElement('mark');
            mark.setAttribute('data-find', 'true');
            mark.style.background = '#fff176';
            mark.style.color = '#000';
            mark.textContent = text.substring(idx, idx + query.length);
            frag.appendChild(mark);
            count++;
            lastIdx = idx + query.length;
            idx = lowerText.indexOf(lowerQuery, lastIdx);
        }

        if (lastIdx < text.length) {
            frag.appendChild(document.createTextNode(text.substring(lastIdx)));
        }

        node.parentNode.replaceChild(frag, node);
    });

    findMatches = Array.from(editor.querySelectorAll('mark[data-find]'));
    findCurrentIndex = findMatches.length > 0 ? 0 : -1;

    if (findCurrentIndex >= 0) {
        highlightCurrentMatch();
    }

    document.getElementById('find-count').textContent =
        count > 0 ? `${findCurrentIndex + 1} of ${count}` : 'No results';
}

function highlightCurrentMatch() {
    findMatches.forEach((m, i) => {
        m.style.background = i === findCurrentIndex ? '#f28b82' : '#fff176';
    });
    if (findMatches[findCurrentIndex]) {
        findMatches[findCurrentIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function findNext() {
    if (findMatches.length === 0) return;
    findCurrentIndex = (findCurrentIndex + 1) % findMatches.length;
    highlightCurrentMatch();
    document.getElementById('find-count').textContent =
        `${findCurrentIndex + 1} of ${findMatches.length}`;
}

function findPrev() {
    if (findMatches.length === 0) return;
    findCurrentIndex = (findCurrentIndex - 1 + findMatches.length) % findMatches.length;
    highlightCurrentMatch();
    document.getElementById('find-count').textContent =
        `${findCurrentIndex + 1} of ${findMatches.length}`;
}

function replaceOne() {
    if (findCurrentIndex < 0 || !findMatches[findCurrentIndex]) return;
    const replaceText = document.getElementById('replace-input').value;
    const mark = findMatches[findCurrentIndex];
    mark.parentNode.replaceChild(document.createTextNode(replaceText), mark);
    findMatches.splice(findCurrentIndex, 1);
    if (findCurrentIndex >= findMatches.length) findCurrentIndex = 0;
    if (findMatches.length > 0) {
        highlightCurrentMatch();
    }
    document.getElementById('find-count').textContent =
        findMatches.length > 0 ? `${findCurrentIndex + 1} of ${findMatches.length}` : 'No results';
    markDirty();
}

function replaceAll() {
    const replaceText = document.getElementById('replace-input').value;
    findMatches.forEach(mark => {
        mark.parentNode.replaceChild(document.createTextNode(replaceText), mark);
    });
    findMatches = [];
    findCurrentIndex = -1;
    document.getElementById('find-count').textContent = 'All replaced';
    markDirty();
}

// === Modals ===
function showModal(id) {
    document.getElementById('modal-overlay').classList.add('show');
    document.getElementById(id).classList.add('show');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('show');
    document.querySelectorAll('.modal').forEach(m => m.classList.remove('show'));
}

// === Menus ===
function closeAllMenus() {
    document.querySelectorAll('.dropdown').forEach(d => d.classList.remove('show'));
}

// === Dark Mode ===
function toggleDarkMode() {
    closeAllMenus();
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('wp_darkmode', document.body.classList.contains('dark-mode'));
}

function loadDarkMode() {
    if (localStorage.getItem('wp_darkmode') === 'true') {
        document.body.classList.add('dark-mode');
    }
}

// === Utility ===
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// === Event Listeners ===

// Editor input
editor.addEventListener('input', () => {
    markDirty();
    updateCounts();
});

// Track cursor position and toolbar state on selection change
document.addEventListener('selectionchange', () => {
    updateToolbarState();
});

// Title change triggers dirty state
docTitle.addEventListener('input', () => {
    markDirty();
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    const mod = e.ctrlKey || e.metaKey;

    if (mod && e.key === 's') {
        e.preventDefault();
        saveDocument();
    } else if (mod && e.key === 'f') {
        e.preventDefault();
        toggleFindBar();
    } else if (mod && e.key === 'h') {
        e.preventDefault();
        toggleFindBar();
        document.getElementById('replace-input').focus();
    } else if (mod && e.key === 'p') {
        e.preventDefault();
        printDocument();
    } else if (e.key === 'Escape') {
        closeFindBar();
        closeModal();
    } else if (e.key === 'Tab' && editor.contains(document.activeElement)) {
        e.preventDefault();
        document.execCommand('insertHTML', false, '&emsp;');
    }
});

// Click outside menus to close
document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu-item')) {
        closeAllMenus();
    }
});

// Paste as plain text option (Ctrl+Shift+V)
editor.addEventListener('paste', (e) => {
    if (e.shiftKey) {
        e.preventDefault();
        const text = e.clipboardData.getData('text/plain');
        document.execCommand('insertText', false, text);
    }
});

// Handle Enter in find input
document.getElementById('find-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        if (e.shiftKey) findPrev();
        else findNext();
    }
});

// === Ruler Generation ===
function buildRuler() {
    const ruler = document.getElementById('ruler');
    let html = '';
    for (let i = 0; i <= 20; i++) {
        const left = i * 96 / 2;
        html += `<span style="position:absolute;left:${left}px;top:6px;font-size:8px;color:var(--text-muted);user-select:none;">${i / 2}"</span>`;
    }
    ruler.innerHTML = html;
}

// === Initialize ===
function init() {
    loadDarkMode();
    buildRuler();
    updateCounts();
    updateToolbarState();

    // Load last session if available
    const docs = getAllDocuments();
    const lastDocId = localStorage.getItem('wp_lastDoc');
    if (lastDocId && docs[lastDocId]) {
        loadDocument(lastDocId);
    }

    // Track last document for session restore
    const origSave = saveDocument;
    const wrappedSave = function() {
        origSave();
        if (currentDocId) {
            localStorage.setItem('wp_lastDoc', currentDocId);
        }
    };
    // Override global reference
    window.saveDocument = wrappedSave;
}

init();
