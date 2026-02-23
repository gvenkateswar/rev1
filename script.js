// ── Constants ────────────────────────────────────────────────────────────────

const DEVICES = {
    macbook:       { label: 'MacBook',      color: '#007AFF' },
    iphone:        { label: 'iPhone',       color: '#34C759' },
    ipad:          { label: 'iPad',         color: '#FF9500' },
    'apple-watch': { label: 'Apple Watch',  color: '#FF2D55' },
};

const CATEGORIES = {
    work:           { label: 'Work',           color: '#007AFF' },
    browsing:       { label: 'Browsing',       color: '#5856D6' },
    'social-media': { label: 'Social Media',   color: '#FF2D55' },
    communication:  { label: 'Communication',  color: '#34C759' },
    entertainment:  { label: 'Entertainment',  color: '#FF9500' },
    fitness:        { label: 'Fitness',        color: '#FF3B30' },
    reading:        { label: 'Reading',        color: '#AF52DE' },
    creative:       { label: 'Creative',       color: '#00C7BE' },
    gaming:         { label: 'Gaming',         color: '#FFD60A' },
    other:          { label: 'Other',          color: '#8E8E93' },
};

const STORAGE_KEY = 'device-usage-data';
const HEALTH_KEY  = 'device-usage-health';
const GOALS_KEY   = 'device-usage-goals';

// ── State ────────────────────────────────────────────────────────────────────

let currentDate = todayString();
let data = loadData();
let healthData = loadHealth();
let goals = loadGoals();

// ── DOM refs ─────────────────────────────────────────────────────────────────

const dateInput      = document.getElementById('date-input');
const prevDayBtn     = document.getElementById('prev-day');
const nextDayBtn     = document.getElementById('next-day');
const usageForm      = document.getElementById('usage-form');
const entriesList    = document.getElementById('entries-list');
const timelineHours  = document.getElementById('timeline-hours');
const breakdownBars  = document.getElementById('breakdown-bars');
const timelineLegend = document.getElementById('timeline-legend');

// Health inputs
const healthInputs = {
    calories: document.getElementById('health-calories'),
    exercise: document.getElementById('health-exercise'),
    stand:    document.getElementById('health-stand'),
    steps:    document.getElementById('health-steps'),
};

const goalInputs = {
    calories: document.getElementById('goal-calories'),
    exercise: document.getElementById('goal-exercise'),
    stand:    document.getElementById('goal-stand'),
    steps:    document.getElementById('goal-steps'),
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function todayString() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function loadData() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch { return {}; }
}

function saveData() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

function loadHealth() {
    try { return JSON.parse(localStorage.getItem(HEALTH_KEY)) || {}; }
    catch { return {}; }
}

function saveHealth() {
    localStorage.setItem(HEALTH_KEY, JSON.stringify(healthData));
}

function loadGoals() {
    try { return JSON.parse(localStorage.getItem(GOALS_KEY)) || { calories: 500, exercise: 30, stand: 12, steps: 10000 }; }
    catch { return { calories: 500, exercise: 30, stand: 12, steps: 10000 }; }
}

function saveGoals() {
    localStorage.setItem(GOALS_KEY, JSON.stringify(goals));
}

function getEntries() {
    return data[currentDate] || [];
}

function getHealth() {
    return healthData[currentDate] || { calories: 0, exercise: 0, stand: 0, steps: 0 };
}

function timeToMinutes(t) {
    const [h, m] = t.split(':').map(Number);
    return h * 60 + m;
}

function minutesToHM(min) {
    const h = Math.floor(min / 60);
    const m = min % 60;
    return `${h}h ${m}m`;
}

function formatTime12(t) {
    const [h, m] = t.split(':').map(Number);
    const period = h >= 12 ? 'PM' : 'AM';
    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
    return `${h12}:${String(m).padStart(2,'0')} ${period}`;
}

function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

// ── Date Navigation ──────────────────────────────────────────────────────────

function setDate(dateStr) {
    currentDate = dateStr;
    dateInput.value = dateStr;
    render();
}

function shiftDate(days) {
    const d = new Date(currentDate + 'T12:00:00');
    d.setDate(d.getDate() + days);
    setDate(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`);
}

// ── Rendering ────────────────────────────────────────────────────────────────

function render() {
    renderTimeline();
    renderSummary();
    renderBreakdown();
    renderEntries();
    renderHealth();
    renderLegend();
}

// Timeline
function renderTimeline() {
    // Hour markers
    timelineHours.innerHTML = '';
    for (let h = 0; h <= 24; h += 3) {
        const mark = document.createElement('span');
        mark.className = 'hour-mark';
        mark.textContent = h === 0 ? '12a' : h < 12 ? `${h}a` : h === 12 ? '12p' : h === 24 ? '12a' : `${h-12}p`;
        mark.style.left = `${(h / 24) * 100}%`;
        timelineHours.appendChild(mark);
    }

    // Render blocks for each device track
    const entries = getEntries();
    Object.keys(DEVICES).forEach(device => {
        const trackEl = document.getElementById(`track-${device}`);
        trackEl.innerHTML = '';

        // Add hour grid lines
        for (let h = 0; h < 24; h += 3) {
            const line = document.createElement('div');
            line.style.cssText = `position:absolute;left:${(h/24)*100}%;top:0;bottom:0;width:1px;background:rgba(0,0,0,0.06);`;
            trackEl.appendChild(line);
        }

        const deviceEntries = entries.filter(e => e.device === device);
        deviceEntries.forEach(entry => {
            const startMin = timeToMinutes(entry.start);
            const endMin = timeToMinutes(entry.end);
            const duration = endMin - startMin;
            if (duration <= 0) return;

            const block = document.createElement('div');
            block.className = 'usage-block';
            const cat = CATEGORIES[entry.category] || CATEGORIES.other;
            block.style.left = `${(startMin / 1440) * 100}%`;
            block.style.width = `${(duration / 1440) * 100}%`;
            block.style.background = cat.color;

            const tooltip = document.createElement('span');
            tooltip.className = 'block-tooltip';
            tooltip.textContent = `${cat.label} ${formatTime12(entry.start)}-${formatTime12(entry.end)}`;
            block.appendChild(tooltip);

            trackEl.appendChild(block);
        });
    });
}

// Legend
function renderLegend() {
    const entries = getEntries();
    const usedCategories = [...new Set(entries.map(e => e.category))];
    timelineLegend.innerHTML = '';

    if (usedCategories.length === 0) {
        timelineLegend.style.display = 'none';
        return;
    }
    timelineLegend.style.display = 'flex';

    usedCategories.forEach(catKey => {
        const cat = CATEGORIES[catKey] || CATEGORIES.other;
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `<span class="legend-dot" style="background:${cat.color}"></span>${cat.label}`;
        timelineLegend.appendChild(item);
    });
}

// Summary Cards
function renderSummary() {
    const entries = getEntries();
    let totalMin = 0;

    Object.keys(DEVICES).forEach(device => {
        const mins = entries
            .filter(e => e.device === device)
            .reduce((sum, e) => {
                const d = timeToMinutes(e.end) - timeToMinutes(e.start);
                return sum + (d > 0 ? d : 0);
            }, 0);

        const elId = device === 'apple-watch' ? 'summary-watch' : `summary-${device}`;
        document.getElementById(elId).textContent = minutesToHM(mins);
        totalMin += mins;
    });

    document.getElementById('summary-total').textContent = minutesToHM(totalMin);
}

// Activity Breakdown
function renderBreakdown() {
    const entries = getEntries();
    const categoryMins = {};
    let maxMin = 0;

    entries.forEach(entry => {
        const dur = timeToMinutes(entry.end) - timeToMinutes(entry.start);
        if (dur <= 0) return;
        categoryMins[entry.category] = (categoryMins[entry.category] || 0) + dur;
        if (categoryMins[entry.category] > maxMin) maxMin = categoryMins[entry.category];
    });

    breakdownBars.innerHTML = '';

    if (Object.keys(categoryMins).length === 0) {
        breakdownBars.innerHTML = '<div class="breakdown-empty">No entries yet. Add usage below.</div>';
        return;
    }

    // Sort by duration descending
    const sorted = Object.entries(categoryMins).sort((a, b) => b[1] - a[1]);

    sorted.forEach(([catKey, mins]) => {
        const cat = CATEGORIES[catKey] || CATEGORIES.other;
        const pct = maxMin > 0 ? (mins / maxMin) * 100 : 0;

        const row = document.createElement('div');
        row.className = 'breakdown-row';
        row.innerHTML = `
            <div class="breakdown-label">${cat.label}</div>
            <div class="breakdown-bar-container">
                <div class="breakdown-bar-fill" style="width:${pct}%;background:${cat.color}"></div>
            </div>
            <div class="breakdown-time">${minutesToHM(mins)}</div>
        `;
        breakdownBars.appendChild(row);
    });
}

// Entries List
function renderEntries() {
    const entries = getEntries();
    entriesList.innerHTML = '';

    if (entries.length === 0) {
        entriesList.innerHTML = '<div class="entries-empty">No entries for this day. Use the form below to log your device usage.</div>';
        return;
    }

    // Sort by start time
    const sorted = [...entries].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));

    sorted.forEach(entry => {
        const device = DEVICES[entry.device] || DEVICES.macbook;
        const cat = CATEGORIES[entry.category] || CATEGORIES.other;
        const dur = timeToMinutes(entry.end) - timeToMinutes(entry.start);

        const item = document.createElement('div');
        item.className = 'entry-item';
        item.innerHTML = `
            <div class="entry-device-dot" data-device="${entry.device}"></div>
            <div class="entry-info">
                <div class="entry-info-top">
                    ${device.label}
                    <span class="entry-category-tag" style="background:${cat.color}">${cat.label}</span>
                </div>
                <div class="entry-info-bottom">${entry.notes || 'No notes'}</div>
            </div>
            <div class="entry-time">${formatTime12(entry.start)} - ${formatTime12(entry.end)} (${minutesToHM(dur > 0 ? dur : 0)})</div>
            <button class="entry-delete" data-id="${entry.id}" title="Delete entry">&times;</button>
        `;
        entriesList.appendChild(item);
    });
}

// Health Rings
function renderHealth() {
    const h = getHealth();

    // Populate inputs
    healthInputs.calories.value = h.calories || '';
    healthInputs.exercise.value = h.exercise || '';
    healthInputs.stand.value    = h.stand || '';
    healthInputs.steps.value    = h.steps || '';

    // Populate goals
    goalInputs.calories.value = goals.calories || '';
    goalInputs.exercise.value = goals.exercise || '';
    goalInputs.stand.value    = goals.stand || '';
    goalInputs.steps.value    = goals.steps || '';

    // Update ring fills
    const circumference = 2 * Math.PI * 42; // ~263.89

    updateRing('move',     h.calories, goals.calories, circumference);
    updateRing('exercise', h.exercise, goals.exercise, circumference);
    updateRing('stand',    h.stand,    goals.stand,    circumference);
    updateRing('steps',    h.steps,    goals.steps,    circumference);
}

function updateRing(name, value, goal, circumference) {
    const fill = document.getElementById(`ring-${name}-fill`);
    const label = document.getElementById(`ring-${name}-value`);

    const pct = goal > 0 ? Math.min(value / goal, 1) : 0;
    const offset = circumference * (1 - pct);

    fill.style.strokeDasharray = circumference;
    fill.style.strokeDashoffset = offset;

    label.textContent = value || 0;
}

// ── Event Handlers ───────────────────────────────────────────────────────────

// Date navigation
dateInput.addEventListener('change', () => setDate(dateInput.value));
prevDayBtn.addEventListener('click', () => shiftDate(-1));
nextDayBtn.addEventListener('click', () => shiftDate(1));

// Add entry
usageForm.addEventListener('submit', (e) => {
    e.preventDefault();

    const device   = document.getElementById('entry-device').value;
    const category = document.getElementById('entry-category').value;
    const start    = document.getElementById('entry-start').value;
    const end      = document.getElementById('entry-end').value;
    const notes    = document.getElementById('entry-notes').value.trim();

    if (!start || !end) return;
    if (timeToMinutes(end) <= timeToMinutes(start)) {
        alert('End time must be after start time.');
        return;
    }

    const entry = { id: generateId(), device, category, start, end, notes };

    if (!data[currentDate]) data[currentDate] = [];
    data[currentDate].push(entry);
    saveData();
    render();

    // Reset form partially (keep device/category for quick re-entry)
    document.getElementById('entry-start').value = end;
    document.getElementById('entry-end').value = '';
    document.getElementById('entry-notes').value = '';
});

// Delete entry
entriesList.addEventListener('click', (e) => {
    const btn = e.target.closest('.entry-delete');
    if (!btn) return;

    const id = btn.dataset.id;
    if (!data[currentDate]) return;

    data[currentDate] = data[currentDate].filter(entry => entry.id !== id);
    if (data[currentDate].length === 0) delete data[currentDate];
    saveData();
    render();
});

// Health inputs
Object.keys(healthInputs).forEach(key => {
    healthInputs[key].addEventListener('input', () => {
        if (!healthData[currentDate]) healthData[currentDate] = { calories: 0, exercise: 0, stand: 0, steps: 0 };
        healthData[currentDate][key] = parseInt(healthInputs[key].value) || 0;
        saveHealth();
        renderHealth();
    });
});

// Goal inputs
Object.keys(goalInputs).forEach(key => {
    goalInputs[key].addEventListener('input', () => {
        goals[key] = parseInt(goalInputs[key].value) || 0;
        saveGoals();
        renderHealth();
    });
});

// Keyboard shortcut: arrow keys for date navigation
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'ArrowLeft') shiftDate(-1);
    if (e.key === 'ArrowRight') shiftDate(1);
});

// ── Init ─────────────────────────────────────────────────────────────────────

setDate(todayString());
