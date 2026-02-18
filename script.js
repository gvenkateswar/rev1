(function () {
    'use strict';

    // --- DOM refs ---
    const apiKeyInput = document.getElementById('api-key-input');
    const btnSaveKey = document.getElementById('btn-save-key');
    const keyStatus = document.getElementById('key-status');

    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const previewContainer = document.getElementById('preview-container');
    const previewImg = document.getElementById('preview-img');
    const btnClearImage = document.getElementById('btn-clear-image');
    const ocrProgress = document.getElementById('ocr-progress');
    const ocrProgressFill = document.getElementById('ocr-progress-fill');
    const ocrStatus = document.getElementById('ocr-status');
    const btnScan = document.getElementById('btn-scan');
    const btnManual = document.getElementById('btn-manual');

    const stepUpload = document.getElementById('step-upload');
    const stepEdit = document.getElementById('step-edit');
    const stepSchedule = document.getElementById('step-schedule');

    const taskList = document.getElementById('task-list');
    const btnAddTask = document.getElementById('btn-add-task');
    const btnBackUpload = document.getElementById('btn-back-upload');
    const btnSchedule = document.getElementById('btn-schedule');

    const scheduleDate = document.getElementById('schedule-date');
    const timeline = document.getElementById('timeline');
    const btnBackEdit = document.getElementById('btn-back-edit');
    const btnDownload = document.getElementById('btn-download');

    // --- State ---
    let uploadedImageData = null; // base64 data URL
    let tasks = []; // { name: string, duration: number (minutes) }
    let scheduledEvents = []; // computed from tasks

    // --- API Key management ---
    var STORAGE_KEY = 'ntc_openai_api_key';

    function loadApiKey() {
        var saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            apiKeyInput.value = saved;
            keyStatus.textContent = 'Saved';
            keyStatus.classList.remove('error');
        }
    }

    function getApiKey() {
        return apiKeyInput.value.trim();
    }

    btnSaveKey.addEventListener('click', function () {
        var key = getApiKey();
        if (!key) {
            keyStatus.textContent = 'Enter a key';
            keyStatus.classList.add('error');
            return;
        }
        localStorage.setItem(STORAGE_KEY, key);
        keyStatus.textContent = 'Saved';
        keyStatus.classList.remove('error');
    });

    loadApiKey();

    // --- Navigation ---
    function showStep(step) {
        [stepUpload, stepEdit, stepSchedule].forEach(function (s) {
            s.classList.remove('active');
            s.classList.add('hidden');
        });
        step.classList.remove('hidden');
        step.classList.add('active');
    }

    // --- Step 1: Image upload ---
    dropZone.addEventListener('click', function () {
        fileInput.click();
    });

    dropZone.addEventListener('dragover', function (e) {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', function () {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', function (e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        var files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('image/')) {
            handleImageFile(files[0]);
        }
    });

    fileInput.addEventListener('change', function () {
        if (fileInput.files.length > 0) {
            handleImageFile(fileInput.files[0]);
        }
    });

    function handleImageFile(file) {
        var reader = new FileReader();
        reader.onload = function (e) {
            uploadedImageData = e.target.result;
            previewImg.src = uploadedImageData;
            previewContainer.classList.remove('hidden');
            dropZone.classList.add('hidden');
            btnScan.disabled = false;
        };
        reader.readAsDataURL(file);
    }

    btnClearImage.addEventListener('click', function () {
        uploadedImageData = null;
        previewImg.src = '';
        previewContainer.classList.add('hidden');
        dropZone.classList.remove('hidden');
        btnScan.disabled = true;
        fileInput.value = '';
    });

    // --- OCR via OpenAI Vision API ---
    btnScan.addEventListener('click', async function () {
        if (!uploadedImageData) return;

        var apiKey = getApiKey();
        if (!apiKey) {
            keyStatus.textContent = 'Key required';
            keyStatus.classList.add('error');
            apiKeyInput.focus();
            return;
        }

        btnScan.disabled = true;
        btnManual.disabled = true;
        ocrProgress.classList.remove('hidden');
        ocrProgressFill.style.width = '30%';
        ocrStatus.textContent = 'Sending image to OpenAI...';

        try {
            var responseText = await callOpenAIVision(apiKey, uploadedImageData);
            ocrProgressFill.style.width = '100%';
            ocrStatus.textContent = 'Done!';

            tasks = parseGPTResponse(responseText);

            if (tasks.length === 0) {
                tasks = [{ name: 'New task', duration: 30 }];
            }

            renderTaskList();
            showStep(stepEdit);
        } catch (err) {
            ocrProgressFill.style.width = '0%';
            ocrStatus.textContent = 'Error: ' + err.message;
        } finally {
            btnScan.disabled = false;
            btnManual.disabled = false;
        }
    });

    async function callOpenAIVision(apiKey, imageDataUrl) {
        var response = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + apiKey
            },
            body: JSON.stringify({
                model: 'gpt-4o',
                messages: [
                    {
                        role: 'system',
                        content: 'You read handwritten notes and extract tasks/to-do items. ' +
                            'Return ONLY a JSON array of objects, each with "name" (string) and "duration" (integer, in minutes). ' +
                            'If a duration is mentioned in the notes, use it. Otherwise estimate a reasonable duration (15-120 min). ' +
                            'Do not include any text outside the JSON array. Example: [{"name":"Write report","duration":60}]'
                    },
                    {
                        role: 'user',
                        content: [
                            {
                                type: 'text',
                                text: 'Read the handwritten notes in this image and extract all tasks/to-do items as a JSON array.'
                            },
                            {
                                type: 'image_url',
                                image_url: { url: imageDataUrl }
                            }
                        ]
                    }
                ],
                max_tokens: 1024,
                temperature: 0.2
            })
        });

        if (!response.ok) {
            var errBody = await response.text();
            var errMsg = 'API error ' + response.status;
            try {
                var errJson = JSON.parse(errBody);
                if (errJson.error && errJson.error.message) {
                    errMsg = errJson.error.message;
                }
            } catch (_) {}
            throw new Error(errMsg);
        }

        var data = await response.json();
        return data.choices[0].message.content;
    }

    // --- Parse GPT JSON response into tasks ---
    function parseGPTResponse(text) {
        // Try to extract JSON array from the response
        var jsonStr = text.trim();
        // Strip markdown code fences if present
        jsonStr = jsonStr.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '');

        try {
            var arr = JSON.parse(jsonStr);
            if (!Array.isArray(arr)) throw new Error('Not an array');
            return arr
                .filter(function (item) {
                    return item && typeof item.name === 'string' && item.name.trim().length > 0;
                })
                .map(function (item) {
                    var dur = parseInt(item.duration, 10);
                    if (isNaN(dur) || dur < 5) dur = 30;
                    if (dur > 480) dur = 480;
                    return { name: item.name.trim(), duration: dur };
                });
        } catch (e) {
            // Fallback: try line-by-line parsing
            return parseTasksFromText(text);
        }
    }

    // --- Fallback: parse tasks from raw text ---
    function parseTasksFromText(text) {
        var lines = text.split('\n')
            .map(function (l) { return l.trim(); })
            .filter(function (l) { return l.length > 0; });

        var parsed = [];
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var cleaned = line
                .replace(/^[\u2022\u2023\u25E6\u2043\u2219\-\*\+]\s*/, '')
                .replace(/^\d+[\.\)]\s*/, '')
                .replace(/^\[[ x]?\]\s*/i, '')
                .trim();

            if (cleaned.length < 2) continue;

            var duration = estimateDuration(cleaned);
            var name = cleaned
                .replace(/\(?\s*\d+\s*(min(utes?)?|hrs?|hours?)\s*\)?/i, '')
                .replace(/\s{2,}/g, ' ')
                .trim();

            if (name.length < 2) continue;

            parsed.push({ name: name, duration: duration });
        }

        return parsed;
    }

    function estimateDuration(text) {
        var match = text.match(/(\d+)\s*(min(utes?)?|hrs?|hours?)/i);
        if (match) {
            var val = parseInt(match[1], 10);
            var unit = match[2].toLowerCase();
            if (unit.startsWith('h')) return val * 60;
            return val;
        }
        return 30;
    }

    // --- Manual entry ---
    btnManual.addEventListener('click', function () {
        tasks = [
            { name: '', duration: 30 },
            { name: '', duration: 30 },
            { name: '', duration: 30 }
        ];
        renderTaskList();
        showStep(stepEdit);
    });

    // --- Step 2: Task editor ---
    function renderTaskList() {
        taskList.innerHTML = '';
        for (var i = 0; i < tasks.length; i++) {
            taskList.appendChild(createTaskRow(i));
        }
    }

    function createTaskRow(index) {
        var task = tasks[index];

        var row = document.createElement('div');
        row.className = 'task-item';
        row.draggable = true;
        row.dataset.index = index;

        var handle = document.createElement('span');
        handle.className = 'drag-handle';
        handle.textContent = '\u2630';

        var nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = task.name;
        nameInput.placeholder = 'Task name';
        nameInput.addEventListener('input', function () {
            tasks[index].name = nameInput.value;
        });

        var durationSelect = document.createElement('select');
        var durations = [15, 30, 45, 60, 90, 120, 180, 240];
        for (var d = 0; d < durations.length; d++) {
            var opt = document.createElement('option');
            opt.value = durations[d];
            opt.textContent = formatDuration(durations[d]);
            if (durations[d] === task.duration) opt.selected = true;
            durationSelect.appendChild(opt);
        }
        if (durations.indexOf(task.duration) === -1) {
            var customOpt = document.createElement('option');
            customOpt.value = task.duration;
            customOpt.textContent = formatDuration(task.duration);
            customOpt.selected = true;
            durationSelect.insertBefore(customOpt, durationSelect.firstChild);
        }
        durationSelect.addEventListener('change', function () {
            tasks[index].duration = parseInt(durationSelect.value, 10);
        });

        var removeBtn = document.createElement('button');
        removeBtn.className = 'btn-remove';
        removeBtn.textContent = '\u00d7';
        removeBtn.addEventListener('click', function () {
            tasks.splice(index, 1);
            renderTaskList();
        });

        row.appendChild(handle);
        row.appendChild(nameInput);
        row.appendChild(durationSelect);
        row.appendChild(removeBtn);

        row.addEventListener('dragstart', function (e) {
            e.dataTransfer.setData('text/plain', index.toString());
            row.style.opacity = '0.5';
        });
        row.addEventListener('dragend', function () {
            row.style.opacity = '1';
        });
        row.addEventListener('dragover', function (e) {
            e.preventDefault();
        });
        row.addEventListener('drop', function (e) {
            e.preventDefault();
            var fromIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);
            var toIndex = index;
            if (fromIndex !== toIndex) {
                var moved = tasks.splice(fromIndex, 1)[0];
                tasks.splice(toIndex, 0, moved);
                renderTaskList();
            }
        });

        return row;
    }

    btnAddTask.addEventListener('click', function () {
        tasks.push({ name: '', duration: 30 });
        renderTaskList();
        var inputs = taskList.querySelectorAll('input[type="text"]');
        if (inputs.length > 0) inputs[inputs.length - 1].focus();
    });

    btnBackUpload.addEventListener('click', function () {
        showStep(stepUpload);
    });

    // --- Step 3: Schedule ---
    btnSchedule.addEventListener('click', function () {
        var validTasks = tasks.filter(function (t) { return t.name.trim().length > 0; });
        if (validTasks.length === 0) {
            alert('Please add at least one task with a name.');
            return;
        }
        tasks = validTasks;

        if (!scheduleDate.value) {
            var today = new Date();
            scheduleDate.value = today.getFullYear() + '-' +
                padZero(today.getMonth() + 1) + '-' +
                padZero(today.getDate());
        }

        buildSchedule();
        showStep(stepSchedule);
    });

    scheduleDate.addEventListener('change', function () {
        buildSchedule();
    });

    function buildSchedule() {
        scheduledEvents = [];
        var startMinutes = 9 * 60;
        var endMinutes = 17 * 60;
        var currentMinutes = startMinutes;
        var overflow = [];

        for (var i = 0; i < tasks.length; i++) {
            var task = tasks[i];
            if (currentMinutes + task.duration <= endMinutes) {
                scheduledEvents.push({
                    name: task.name,
                    startMinutes: currentMinutes,
                    duration: task.duration,
                    overflow: false
                });
                currentMinutes += task.duration;

                if (i < tasks.length - 1 && currentMinutes + 10 <= endMinutes) {
                    scheduledEvents.push({
                        name: 'Break',
                        startMinutes: currentMinutes,
                        duration: 10,
                        isBreak: true,
                        overflow: false
                    });
                    currentMinutes += 10;
                }
            } else if (currentMinutes < endMinutes) {
                var remaining = endMinutes - currentMinutes;
                scheduledEvents.push({
                    name: task.name,
                    startMinutes: currentMinutes,
                    duration: remaining,
                    overflow: false,
                    truncated: true
                });
                currentMinutes = endMinutes;
                overflow.push(task.name + ' (needs ' + formatDuration(task.duration - remaining) + ' more)');
            } else {
                overflow.push(task.name + ' (' + formatDuration(task.duration) + ')');
            }
        }

        renderTimeline(overflow);
    }

    function renderTimeline(overflow) {
        timeline.innerHTML = '';

        for (var i = 0; i < scheduledEvents.length; i++) {
            var ev = scheduledEvents[i];
            var slot = document.createElement('div');
            slot.className = 'timeline-slot' + (ev.isBreak ? ' slot-break' : '');

            var timeEl = document.createElement('div');
            timeEl.className = 'timeline-time';
            timeEl.textContent = minutesToTimeStr(ev.startMinutes) + ' \u2013 ' +
                minutesToTimeStr(ev.startMinutes + ev.duration);

            var taskEl = document.createElement('div');
            taskEl.className = 'timeline-task';
            taskEl.textContent = ev.name + (ev.truncated ? ' (truncated)' : '');

            var durEl = document.createElement('div');
            durEl.className = 'timeline-duration';
            durEl.textContent = formatDuration(ev.duration);

            slot.appendChild(timeEl);
            slot.appendChild(taskEl);
            if (!ev.isBreak) slot.appendChild(durEl);
            timeline.appendChild(slot);
        }

        if (overflow.length > 0) {
            var warn = document.createElement('div');
            warn.className = 'timeline-overflow';
            warn.innerHTML = '<strong>Could not fit:</strong> ' +
                overflow.map(function (t) { return escapeHtml(t); }).join(', ');
            timeline.appendChild(warn);
        }
    }

    btnBackEdit.addEventListener('click', function () {
        showStep(stepEdit);
        renderTaskList();
    });

    // --- ICS Generation ---
    btnDownload.addEventListener('click', function () {
        var dateStr = scheduleDate.value;
        if (!dateStr) {
            alert('Please select a date.');
            return;
        }

        var icsContent = generateICS(dateStr);
        var blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
        var url = URL.createObjectURL(blob);

        var a = document.createElement('a');
        a.href = url;
        a.download = 'schedule-' + dateStr + '.ics';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    function generateICS(dateStr) {
        var parts = dateStr.split('-');
        var year = parts[0];
        var month = parts[1];
        var day = parts[2];

        var lines = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//NotesToCalendar//EN',
            'CALSCALE:GREGORIAN',
            'METHOD:PUBLISH'
        ];

        for (var i = 0; i < scheduledEvents.length; i++) {
            var ev = scheduledEvents[i];
            if (ev.isBreak) continue;

            var startH = Math.floor(ev.startMinutes / 60);
            var startM = ev.startMinutes % 60;
            var endTotal = ev.startMinutes + ev.duration;
            var endH = Math.floor(endTotal / 60);
            var endM = endTotal % 60;

            var dtStart = year + month + day + 'T' + padZero(startH) + padZero(startM) + '00';
            var dtEnd = year + month + day + 'T' + padZero(endH) + padZero(endM) + '00';
            var uid = 'ntc-' + dateStr + '-' + i + '@notestocalendar';
            var now = new Date();
            var dtstamp = now.getUTCFullYear() +
                padZero(now.getUTCMonth() + 1) +
                padZero(now.getUTCDate()) + 'T' +
                padZero(now.getUTCHours()) +
                padZero(now.getUTCMinutes()) +
                padZero(now.getUTCSeconds()) + 'Z';

            lines.push('BEGIN:VEVENT');
            lines.push('UID:' + uid);
            lines.push('DTSTAMP:' + dtstamp);
            lines.push('DTSTART:' + dtStart);
            lines.push('DTEND:' + dtEnd);
            lines.push('SUMMARY:' + escapeICSText(ev.name));
            if (ev.truncated) {
                lines.push('DESCRIPTION:This task was truncated to fit the 9-5 window.');
            }
            lines.push('END:VEVENT');
        }

        lines.push('END:VCALENDAR');
        return lines.join('\r\n');
    }

    // --- Helpers ---
    function padZero(n) {
        return n < 10 ? '0' + n : '' + n;
    }

    function formatDuration(minutes) {
        if (minutes < 60) return minutes + ' min';
        var h = Math.floor(minutes / 60);
        var m = minutes % 60;
        if (m === 0) return h + 'h';
        return h + 'h ' + m + 'm';
    }

    function minutesToTimeStr(totalMinutes) {
        var h = Math.floor(totalMinutes / 60);
        var m = totalMinutes % 60;
        var ampm = h >= 12 ? 'PM' : 'AM';
        var displayH = h > 12 ? h - 12 : (h === 0 ? 12 : h);
        return displayH + ':' + padZero(m) + ' ' + ampm;
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeICSText(str) {
        return str.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
    }
})();
