'use strict';

// ── State ────────────────────────────────────────────────────────────────────
let meta = null;        // {valid, survey_id, class_name, survey_title, questionnaire}
let tan = null;
let answers = {};       // {question_id: value}
let currentSection = 0;
let questionnaire = null;
let allSections = [];   // [{id, title, questions:[...]}]
let flatQuestions = []; // all questions in order

// ── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  tan = sessionStorage.getItem('survey_tan');
  const metaRaw = sessionStorage.getItem('survey_meta');

  if (!tan || !metaRaw) {
    showError('Keine TAN gefunden. Bitte gehe zur Startseite zurück.');
    return;
  }

  try {
    meta = JSON.parse(metaRaw);
  } catch (e) {
    showError('Fehler beim Laden der Befragungsdaten.');
    return;
  }

  questionnaire = meta.questionnaire;
  allSections = questionnaire.sections || [];

  // Kinder-Befragung: Grundschrift-Klasse setzen
  if (questionnaire.id && questionnaire.id.startsWith('kinder')) {
    document.body.classList.add('kinder-survey');
  }

  // Flatten questions for progress counting
  allSections.forEach(sec => {
    sec.questions.forEach(q => flatQuestions.push(q));
  });

  // Check for draft
  const draftKey = 'survey_draft_' + simpleHash(tan);
  const draftRaw = localStorage.getItem(draftKey);

  if (draftRaw) {
    try {
      const draft = JSON.parse(draftRaw);
      document.getElementById('loading-screen').style.display = 'none';
      document.getElementById('draft-prompt').style.display = '';
      document.getElementById('draft-continue').onclick = function () {
        answers = draft.answers || {};
        currentSection = draft.section || 0;
        document.getElementById('draft-prompt').style.display = 'none';
        showSurvey();
      };
      document.getElementById('draft-restart').onclick = function () {
        localStorage.removeItem(draftKey);
        answers = {};
        currentSection = 0;
        document.getElementById('draft-prompt').style.display = 'none';
        showSurvey();
      };
      return;
    } catch (e) {
      localStorage.removeItem(draftKey);
    }
  }

  document.getElementById('loading-screen').style.display = 'none';
  showSurvey();
});

// ── Show survey ───────────────────────────────────────────────────────────────
function showSurvey() {
  document.getElementById('survey-screen').style.display = '';
  document.getElementById('survey-title').textContent = meta.survey_title || questionnaire.title;
  renderSection();

  document.getElementById('btn-back').addEventListener('click', goBack);
  document.getElementById('btn-next').addEventListener('click', goNext);
  document.getElementById('btn-submit').addEventListener('click', submitSurvey);
  document.getElementById('btn-save').addEventListener('click', saveDraft);
}

// ── Render section ───────────────────────────────────────────────────────────
function renderSection() {
  const sec = allSections[currentSection];
  document.getElementById('section-label').textContent = sec.title;

  const container = document.getElementById('questions-container');
  container.innerHTML = '';

  const visibleQs = sec.questions.filter(q => isVisible(q));

  visibleQs.forEach(q => {
    container.appendChild(buildQuestionBlock(q));
  });

  // Nav buttons
  const btnBack = document.getElementById('btn-back');
  const btnNext = document.getElementById('btn-next');
  const btnSubmit = document.getElementById('btn-submit');
  const isLast = currentSection === allSections.length - 1;

  btnBack.style.display = currentSection > 0 ? '' : 'none';
  btnNext.style.display = isLast ? 'none' : '';
  btnSubmit.style.display = isLast ? '' : 'none';

  updateProgress();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Build question block ──────────────────────────────────────────────────────
function buildQuestionBlock(q) {
  const div = document.createElement('div');
  div.className = 'question-block';
  div.dataset.qid = q.id;

  const textEl = document.createElement('p');
  textEl.className = 'question-text';
  textEl.textContent = q.text;
  div.appendChild(textEl);

  if (q.type === 'scale') {
    const opts = questionnaire.scale.options;
    div.appendChild(buildChoiceOptions(q, opts, true));
  } else if (q.type === 'single_choice') {
    div.appendChild(buildChoiceOptions(q, q.options, false));
  } else if (q.type === 'text') {
    const ta = document.createElement('textarea');
    ta.className = 'freitext-area';
    ta.placeholder = 'Deine Antwort (optional)';
    ta.rows = 4;
    ta.value = answers[q.id] || '';
    ta.addEventListener('input', function () {
      answers[q.id] = ta.value.trim() || undefined;
    });
    div.appendChild(ta);
    const hint = document.createElement('p');
    hint.className = 'optional-hint';
    hint.textContent = 'Diese Frage ist freiwillig.';
    div.appendChild(hint);
  }

  return div;
}

// colorCode=true für Skalen (grün→rot), false für single_choice
function buildChoiceOptions(q, options, colorCode) {
  const wrap = document.createElement('div');
  wrap.className = 'answer-options';

  options.forEach((opt, idx) => {
    const label = document.createElement('label');
    const isSelected = answers[q.id] === opt.value;
    label.className = 'answer-option' +
      (isSelected ? ' selected' : '') +
      (colorCode ? '' : ' no-color-code');
    if (colorCode) label.dataset.optIndex = idx;

    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = q.id;
    radio.value = opt.value;
    radio.checked = isSelected;

    radio.addEventListener('change', function () {
      answers[q.id] = opt.value;
      wrap.querySelectorAll('.answer-option').forEach(el => el.classList.remove('selected'));
      label.classList.add('selected');
      label.closest('.question-block').classList.remove('required-error');
      reRenderConditionals();
    });

    const span = document.createElement('span');
    span.textContent = opt.label;

    label.appendChild(radio);
    label.appendChild(span);
    wrap.appendChild(label);
  });

  return wrap;
}

// ── Conditional logic ─────────────────────────────────────────────────────────
function isVisible(q) {
  if (!q.show_if) return true;
  const cond = q.show_if;
  if (cond.any_of) {
    return cond.any_of.some(c => {
      const val = answers[c.question];
      if (val === undefined || val === null) return false;
      if ('not_equals' in c) return val !== c.not_equals;
      if ('equals' in c) return val === c.equals;
      return false;
    });
  }
  if (cond.all_of) {
    return cond.all_of.every(c => {
      const val = answers[c.question];
      if (val === undefined || val === null) return false;
      if ('not_equals' in c) return val !== c.not_equals;
      if ('equals' in c) return val === c.equals;
      return false;
    });
  }
  return true;
}

function reRenderConditionals() {
  const sec = allSections[currentSection];
  const container = document.getElementById('questions-container');
  const existingIds = new Set(
    [...container.querySelectorAll('[data-qid]')].map(el => el.dataset.qid)
  );

  sec.questions.forEach(q => {
    const visible = isVisible(q);
    const exists = existingIds.has(q.id);
    if (visible && !exists) {
      const allQids = sec.questions.map(x => x.id);
      const idx = allQids.indexOf(q.id);
      const block = buildQuestionBlock(q);
      let inserted = false;
      for (let i = idx + 1; i < allQids.length; i++) {
        const el = container.querySelector(`[data-qid="${allQids[i]}"]`);
        if (el) { container.insertBefore(block, el); inserted = true; break; }
      }
      if (!inserted) container.appendChild(block);
    } else if (!visible && exists) {
      const el = container.querySelector(`[data-qid="${q.id}"]`);
      if (el) el.remove();
      delete answers[q.id];
    }
  });
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goNext() {
  if (!validateSection()) return;
  if (currentSection < allSections.length - 1) {
    currentSection++;
    renderSection();
  }
}

function goBack() {
  if (currentSection > 0) {
    currentSection--;
    renderSection();
  }
}

function validateSection() {
  const sec = allSections[currentSection];
  let valid = true;
  // Remove old error states first
  document.querySelectorAll('.required-error').forEach(el => el.classList.remove('required-error'));

  sec.questions.forEach(q => {
    if (!isVisible(q)) return;
    if (q.type === 'text') return; // optional
    if (!answers[q.id]) {
      const block = document.querySelector(`[data-qid="${q.id}"]`);
      if (block) block.classList.add('required-error');
      valid = false;
    }
  });
  if (!valid) {
    const firstErr = document.querySelector('.required-error');
    if (firstErr) firstErr.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  return valid;
}

// ── Progress ──────────────────────────────────────────────────────────────────
function updateProgress() {
  const total = allSections.length;
  const pct = Math.round(((currentSection + 1) / total) * 100);
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('progress-label').textContent =
    `Abschnitt ${currentSection + 1} von ${total}`;
}

// ── Save draft ────────────────────────────────────────────────────────────────
function saveDraft() {
  const draftKey = 'survey_draft_' + simpleHash(tan);
  localStorage.setItem(draftKey, JSON.stringify({ answers, section: currentSection }));
  showSaveInfoDialog();
}

function showSaveInfoDialog() {
  // Overlay entfernen falls noch vorhanden
  const existing = document.getElementById('save-info-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'save-info-overlay';
  overlay.className = 'save-info-overlay';

  overlay.innerHTML = `
    <div class="save-info-box">
      <h3>💾 Antworten gespeichert</h3>
      <p>Deine bisherigen Antworten wurden <strong>nur auf diesem Gerät</strong> in deinem Browser gespeichert. Sie sind nicht auf dem Server hinterlegt.</p>
      <p><strong>So setzt du die Befragung fort:</strong><br>
        Öffne diese Seite auf <strong>demselben Gerät und im selben Browser</strong> erneut und gib deine TAN ein. Du wirst dann gefragt, ob du weitermachen möchtest.</p>
      <button class="btn btn-primary" id="save-info-close">Verstanden</button>
    </div>
  `;

  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  document.getElementById('save-info-close').addEventListener('click', close);
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
}

// ── Submit ────────────────────────────────────────────────────────────────────
async function submitSurvey() {
  if (!validateSection()) return;

  const btn = document.getElementById('btn-submit');
  btn.disabled = true;
  btn.textContent = 'Wird gesendet …';

  try {
    const res = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tan: tan, answers: answers })
    });
    const data = await res.json();

    if (data.ok) {
      localStorage.removeItem('survey_draft_' + simpleHash(tan));
      sessionStorage.removeItem('survey_tan');
      sessionStorage.removeItem('survey_meta');
      window.location.href = '/danke';
    } else {
      showError(data.error || 'Beim Senden ist ein Fehler aufgetreten.');
      btn.disabled = false;
      btn.textContent = 'Absenden';
    }
  } catch (e) {
    showError('Netzwerkfehler. Bitte versuche es erneut.');
    btn.disabled = false;
    btn.textContent = 'Absenden';
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function showError(msg) {
  document.getElementById('loading-screen').style.display = 'none';
  document.getElementById('survey-screen').style.display = 'none';
  document.getElementById('draft-prompt').style.display = 'none';
  document.getElementById('error-screen').style.display = '';
  document.getElementById('error-text').textContent = msg;
}

function simpleHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h).toString(36);
}
