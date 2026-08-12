// Corrector AI — Application JavaScript
// Même origine en déploiement (Render, Docker, HTTPS) ; repli pratique pour l'ouverture directe du fichier en local.
const API = window.location.protocol === 'file:' ? 'http://localhost:8000' : window.location.origin;
let token = localStorage.getItem('token');
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let currentExamId = null;
let ocrData = null;
let currentSubjectId = null;   // ID du sujet validé (si utilisé)
let currentBareme = null;       // barème en cours d'édition

// ━━━ API Helper ━━━
async function api(path, opts = {}) {
  const headers = { ...opts.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { logout(); return null; }
  if (res.headers.get('content-type')?.includes('application/json')) return res.json();
  return res;
}

// ━━━ Auth ━━━
function showRegister() { document.getElementById('auth-form-login').style.display='none'; document.getElementById('auth-form-register').style.display='block'; }
function showLogin() { document.getElementById('auth-form-register').style.display='none'; document.getElementById('auth-form-login').style.display='block'; }

async function doLogin() {
  const email = document.getElementById('login-email').value;
  const password = document.getElementById('login-password').value;
  if (!email || !password) return toast('Remplissez tous les champs', 'error');
  const data = await api('/api/auth/login', { method: 'POST', body: { email, password } });
  if (!data || data.detail) return toast(data?.detail || 'Erreur de connexion', 'error');
  token = data.token;
  currentUser = { id: data.id, nom: data.nom, prenom: data.prenom, email };
  localStorage.setItem('token', token);
  localStorage.setItem('user', JSON.stringify(currentUser));
  enterApp();
}

async function doRegister() {
  const nom = document.getElementById('reg-nom').value;
  const prenom = document.getElementById('reg-prenom').value;
  const email = document.getElementById('reg-email').value;
  const password = document.getElementById('reg-password').value;
  if (!nom || !prenom || !email || !password) return toast('Remplissez tous les champs', 'error');
  const data = await api('/api/auth/register', { method: 'POST', body: { nom, prenom, email, password } });
  if (!data || data.detail) return toast(data?.detail || 'Erreur', 'error');
  token = data.token;
  currentUser = { id: data.id, nom, prenom, email };
  localStorage.setItem('token', token);
  localStorage.setItem('user', JSON.stringify(currentUser));
  enterApp();
}

function logout() {
  token = null; currentUser = null;
  localStorage.removeItem('token'); localStorage.removeItem('user');
  document.getElementById('auth-page').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
}

function enterApp() {
  document.getElementById('auth-page').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  if (currentUser) {
    document.getElementById('user-name').textContent = `${currentUser.prenom} ${currentUser.nom}`;
    document.getElementById('user-email').textContent = currentUser.email;
    document.getElementById('user-avatar').textContent = (currentUser.prenom[0] + currentUser.nom[0]).toUpperCase();
  }
  navigate('dashboard');
}

// ━━━ Navigation ━━━
function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.sidebar nav a').forEach(a => a.classList.remove('active'));
  const el = document.getElementById('page-' + page);
  if (el) el.classList.add('active');
  const link = document.querySelector(`[data-page="${page}"]`);
  if (link) link.classList.add('active');
  if (page === 'dashboard') loadDashboard();
  else if (page === 'eleves') loadStudents();
  else if (page === 'corriger') initCorrection();
  else if (page === 'historique') loadHistory();
  else if (page === 'pilote') loadPilot();
}

document.querySelectorAll('.sidebar nav a').forEach(a => {
  a.addEventListener('click', e => { e.preventDefault(); navigate(a.dataset.page); document.querySelector('.sidebar').classList.remove('open'); });
});

// ━━━ Toast ━━━
function toast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.className = 'toast show ' + type;
  document.getElementById('toast-msg').textContent = msg;
  setTimeout(() => t.className = 'toast', 3000);
}

// ━━━ Modal ━━━
function closeModal(id) { document.getElementById(id).classList.remove('show'); }
function openModal(id) { document.getElementById(id).classList.add('show'); }

// ━━━ Dashboard ━━━
async function loadDashboard() {
  const data = await api('/api/stats/dashboard');
  if (!data) return;
  document.getElementById('kpi-exams').textContent = data.nb_exams;
  document.getElementById('kpi-students').textContent = data.nb_students;
  document.getElementById('kpi-avg').textContent = data.moyenne_generale > 0 ? data.moyenne_generale + '/20' : '—';
  document.getElementById('kpi-alerts').textContent = data.nb_alertes;
  // Dernières copies
  const tbody = document.getElementById('recent-exams');
  tbody.innerHTML = '';
  (data.recent_exams || []).forEach(e => {
    tbody.innerHTML += `<tr><td>${e.prenom} ${e.nom}</td><td>${e.matiere}</td><td><span class="badge ${e.note_totale/e.note_sur>=0.5?'badge-success':'badge-danger'}">${e.note_totale}/${e.note_sur}</span></td><td>${e.date_examen||'—'}</td></tr>`;
  });
  if (!data.recent_exams?.length) tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Aucune correction pour l\'instant</td></tr>';
  // Chart
  drawBarChart('chart-matieres', data.moyennes_par_matiere || []);
}

function drawBarChart(canvasId, matieres) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr;
  canvas.style.width = rect.width + 'px'; canvas.style.height = rect.height + 'px';
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height;
  ctx.clearRect(0, 0, W, H);
  if (!matieres.length) { ctx.fillStyle = '#94A3B8'; ctx.font = '14px DM Sans'; ctx.textAlign = 'center'; ctx.fillText('Pas encore de données', W/2, H/2); return; }
  const pad = 40, barW = Math.min(60, (W - pad*2) / matieres.length - 10);
  const maxVal = 20;
  matieres.forEach((m, i) => {
    const x = pad + i * (barW + 10);
    const barH = (m.moyenne / maxVal) * (H - pad * 2);
    const y = H - pad - barH;
    const grad = ctx.createLinearGradient(x, y, x, H - pad);
    grad.addColorStop(0, '#0EA5E9'); grad.addColorStop(1, '#6366F1');
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.roundRect(x, y, barW, barH, [4,4,0,0]); ctx.fill();
    ctx.fillStyle = '#E2E8F0'; ctx.font = 'bold 12px DM Sans'; ctx.textAlign = 'center';
    ctx.fillText(m.moyenne.toFixed(1), x + barW/2, y - 6);
    ctx.fillStyle = '#94A3B8'; ctx.font = '10px DM Sans';
    ctx.fillText(m.matiere.substring(0,8), x + barW/2, H - pad + 16);
  });
}

// ━━━ Correction ━━━
let currentStep = 0;

async function initCorrection() {
  currentStep = 0; ocrData = null; currentExamId = null; currentSubjectId = null; currentBareme = null;
  updateSteps();
  // Reset étape 0
  resetSubject();
  // Charger les élèves dans le select
  const data = await api('/api/students/');
  const sel = document.getElementById('corr-student');
  sel.innerHTML = '<option value="">Sélectionner un élève...</option>';
  (data?.students || []).forEach(s => {
    sel.innerHTML += `<option value="${s.id}">${s.prenom} ${s.nom} (${s.classe})</option>`;
  });
  document.getElementById('corr-date').value = new Date().toISOString().split('T')[0];
  // Reset exercises
  document.getElementById('exercises-list').innerHTML = '';
  exerciseCount = 0;
  addExercise(); addExercise();
}

function updateSteps() {
  document.querySelectorAll('.step').forEach(s => {
    const n = parseInt(s.dataset.step);
    s.classList.remove('active', 'done');
    if (n === currentStep) s.classList.add('active');
    else if (n < currentStep) s.classList.add('done');
  });
  document.querySelectorAll('.step-content').forEach(c => c.style.display = 'none');
  const el = document.getElementById('step-' + currentStep);
  if (el) el.style.display = 'block';
}

async function goStep(n) {
  if (n === 2 && currentStep === 1) {
    if (!document.getElementById('corr-student').value) return toast('Sélectionnez un élève', 'error');
    if (!document.getElementById('corr-matiere').value) return toast('Indiquez la matière', 'error');
  }
  if (n === 4 && currentStep === 3) {
    // Lancer la correction
    currentStep = 4; updateSteps();
    await runGrading();
    return;
  }
  currentStep = n; updateSteps();
}

// ━━━ Étape 0 — Import sujet + génération barème IA ━━━

function resetSubject() {
  currentSubjectId = null; currentBareme = null;
  const inp = document.getElementById('subject-file-input'); if (inp) inp.value = '';
  const analyzing = document.getElementById('subject-analyzing'); if (analyzing) analyzing.style.display = 'none';
  const bareme = document.getElementById('subject-bareme'); if (bareme) bareme.style.display = 'none';
  const dz = document.getElementById('dropzone-subject'); if (dz) dz.style.display = 'block';
}

function skipSubject() { goStep(1); }

function handleSubjectFileSelect(e) { if (e.target.files[0]) uploadSubject(e.target.files[0]); }

async function uploadSubject(file) {
  document.getElementById('dropzone-subject').style.display = 'none';
  document.getElementById('subject-analyzing').style.display = 'block';
  document.getElementById('subject-bareme').style.display = 'none';

  const fd = new FormData(); fd.append('file', file);
  const data = await api('/api/subjects/parse', { method: 'POST', body: fd });
  document.getElementById('subject-analyzing').style.display = 'none';

  if (!data || data.detail) {
    toast(data?.detail || "Erreur lors de l'analyse du sujet", 'error');
    resetSubject();
    return;
  }
  currentBareme = data;
  renderBareme(data);
  toast('Barème généré !');
}

function renderBareme(bareme) {
  // Badge confiance
  const conf = typeof bareme.confiance === 'number' ? bareme.confiance : 0;
  const pct = Math.round(conf * 100);
  let badgeCls = 'badge-danger', msg = 'Correction manuelle recommandée';
  if (conf >= 0.85) { badgeCls = 'badge-success'; msg = 'Barème détecté automatiquement'; }
  else if (conf >= 0.6) { badgeCls = 'badge-warning'; msg = 'Vérifiez les points'; }
  const matiere = bareme.matiere_detectee || '—';
  const niveau = bareme.niveau_detecte || '—';
  document.getElementById('bareme-confidence').innerHTML =
    `<span class="badge ${badgeCls}">${msg} (${pct}%)</span>
     <span class="text-sm text-muted" style="margin-left:12px">Matière : <b>${matiere}</b> · Niveau : <b>${niveau}</b></span>
     ${bareme.remarques ? `<div class="text-sm text-muted mt-8">${bareme.remarques}</div>` : ''}`;

  // Pré-remplir métadonnées correction
  if (bareme.matiere_detectee && !document.getElementById('corr-matiere').value)
    document.getElementById('corr-matiere').value = bareme.matiere_detectee;
  if (bareme.niveau_detecte && !document.getElementById('corr-niveau').value)
    document.getElementById('corr-niveau').value = bareme.niveau_detecte;

  // Construction des lignes éditables
  const tbody = document.getElementById('bareme-tbody');
  tbody.innerHTML = '';
  (bareme.exercices || []).forEach(ex => addBaremeRow(ex));
  updateBaremeTotal();
  document.getElementById('subject-bareme').style.display = 'block';
}

function addBaremeRow(ex = null) {
  const tbody = document.getElementById('bareme-tbody');
  const tr = document.createElement('tr');
  const numero = ex?.numero ?? (tbody.children.length + 1);
  tr.innerHTML = `
    <td><input type="number" class="br-num" value="${numero}" min="1" style="width:55px"></td>
    <td><textarea class="br-enonce" rows="2">${escapeHtml(ex?.enonce || '')}</textarea></td>
    <td><textarea class="br-reponse" rows="2">${escapeHtml(ex?.reponse_attendue || '')}</textarea></td>
    <td><input type="number" class="br-points" value="${ex?.points_max ?? 0}" min="0" step="0.5" style="width:80px" oninput="updateBaremeTotal()"></td>
    <td><button class="btn btn-sm btn-danger" onclick="this.closest('tr').remove(); updateBaremeTotal();">✕</button></td>`;
  tbody.appendChild(tr);
  updateBaremeTotal();
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }

function updateBaremeTotal() {
  let total = 0;
  document.querySelectorAll('#bareme-tbody .br-points').forEach(i => { total += parseFloat(i.value) || 0; });
  document.getElementById('bareme-total').textContent = total.toFixed(1);
}

function collectBaremeRows() {
  const rows = document.querySelectorAll('#bareme-tbody tr');
  const exercices = [];
  rows.forEach(tr => {
    exercices.push({
      numero: parseInt(tr.querySelector('.br-num').value || 0),
      enonce: tr.querySelector('.br-enonce').value || '',
      reponse_attendue: tr.querySelector('.br-reponse').value || '',
      points_max: parseFloat(tr.querySelector('.br-points').value || 0),
      type: 'autre',
      sous_questions: [],
    });
  });
  return exercices;
}

async function validateBareme() {
  const exercices = collectBaremeRows();
  if (!exercices.length) return toast('Ajoutez au moins un exercice', 'error');
  const total = exercices.reduce((s, e) => s + (e.points_max || 0), 0);
  const payload = {
    matiere: currentBareme?.matiere_detectee || document.getElementById('corr-matiere').value || '',
    niveau: currentBareme?.niveau_detecte || document.getElementById('corr-niveau').value || '',
    titre: '',
    total_points: total,
    exercices,
    pdf_path: currentBareme?.pdf_path || '',
  };
  const data = await api('/api/subjects/validate', { method: 'POST', body: payload });
  if (!data || data.detail) return toast(data?.detail || 'Erreur sauvegarde', 'error');
  currentSubjectId = data.subject_id;

  // Pré-remplir les exercices de l'étape 3 à partir du barème validé
  prefillExercisesFromBareme(exercices);

  // Pré-remplir note_sur si total cohérent
  if (total > 0) document.getElementById('corr-notesur').value = total;

  toast('Barème validé — sujet enregistré');
  goStep(1);
}

function prefillExercisesFromBareme(exercices) {
  const list = document.getElementById('exercises-list');
  list.innerHTML = '';
  exerciseCount = 0;
  exercices.forEach((ex, idx) => {
    addExercise();
    const n = idx + 1;
    const enonceEl = document.getElementById(`ex-enonce-${n}`);
    const attendueEl = document.getElementById(`ex-attendue-${n}`);
    const ptsEl = document.getElementById(`ex-points-${n}`);
    if (enonceEl) enonceEl.value = ex.enonce || '';
    if (attendueEl) attendueEl.value = ex.reponse_attendue || '';
    if (ptsEl) ptsEl.value = ex.points_max || 0;
  });
}

// Drag & drop sujet
const dzSubj = document.getElementById('dropzone-subject');
if (dzSubj) {
  dzSubj.addEventListener('dragover', e => { e.preventDefault(); dzSubj.classList.add('dragover'); });
  dzSubj.addEventListener('dragleave', () => dzSubj.classList.remove('dragover'));
  dzSubj.addEventListener('drop', e => { e.preventDefault(); dzSubj.classList.remove('dragover'); if (e.dataTransfer.files[0]) uploadSubject(e.dataTransfer.files[0]); });
}

// Drag & drop
const dz = document.getElementById('dropzone');
if (dz) {
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
  dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('dragover'); if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]); });
}

function handleFileSelect(e) { if (e.target.files[0]) uploadFile(e.target.files[0]); }

async function uploadFile(file) {
  toast('OCR en cours...');
  const fd = new FormData(); fd.append('file', file);
  const data = await api('/api/ocr/extract', { method: 'POST', body: fd });
  if (!data) return toast('Erreur OCR', 'error');
  ocrData = data;
  document.getElementById('ocr-preview').style.display = 'block';
  let html = '';
  (data.exercices || []).forEach(ex => {
    html += `<b>Exercice ${ex.numero}</b> (lisibilité: ${ex.lisibilite})\n${ex.texte_brut}\n\n`;
  });
  document.getElementById('ocr-result').textContent = html;
  // Pré-remplir les réponses élève
  (data.exercices || []).forEach((ex, i) => {
    const textarea = document.querySelector(`#ex-reponse-${i+1}`);
    if (textarea) textarea.value = ex.texte_brut;
  });
  toast('Texte extrait avec succès');
}

// Exercices
let exerciseCount = 0;
function addExercise() {
  exerciseCount++;
  const n = exerciseCount;
  const list = document.getElementById('exercises-list');
  const div = document.createElement('div');
  div.className = 'exercise-item';
  div.id = `exercise-${n}`;
  div.innerHTML = `<h4>Exercice ${n} <button class="btn btn-danger btn-sm" onclick="this.closest('.exercise-item').remove()">✕</button></h4>
<div class="fields"><div class="field"><label>Énoncé</label><textarea id="ex-enonce-${n}" rows="2" placeholder="Question posée à l'élève..."></textarea></div>
<div class="field"><label>Réponse attendue</label><textarea id="ex-attendue-${n}" rows="2" placeholder="Réponse correcte..."></textarea></div>
<div class="field"><label>Réponse de l'élève</label><textarea id="ex-reponse-${n}" rows="2" placeholder="Ce que l'élève a écrit..."></textarea></div>
<div class="field"><label>Points max</label><input type="number" id="ex-points-${n}" value="5" min="0" step="0.5"></div></div>`;
  list.appendChild(div);
}

async function runGrading() {
  const items = document.querySelectorAll('.exercise-item');
  const corrige = [], reponses = [];
  let num = 0;
  items.forEach(item => {
    num++;
    const id = item.id.split('-')[1];
    corrige.push({ numero: num, enonce: item.querySelector('textarea[id^="ex-enonce"]')?.value || '', reponse_attendue: item.querySelector('textarea[id^="ex-attendue"]')?.value || '', points_max: parseFloat(item.querySelector('input[id^="ex-points"]')?.value || 5) });
    reponses.push({ numero: num, reponse_eleve: item.querySelector('textarea[id^="ex-reponse"]')?.value || '' });
  });
  const body = {
    student_id: parseInt(document.getElementById('corr-student').value),
    matiere: document.getElementById('corr-matiere').value,
    niveau: document.getElementById('corr-niveau').value,
    date_examen: document.getElementById('corr-date').value,
    note_sur: parseFloat(document.getElementById('corr-notesur').value || 20),
    image_path: ocrData?.image_path || '',
    exercices_corrige: corrige,
    reponses_eleve: reponses,
  };
  // Si un barème a été validé depuis un sujet, on transmet l'ID
  if (currentSubjectId) body.subject_id = currentSubjectId;
  const data = await api('/api/grading/grade', { method: 'POST', body });
  if (!data || data.detail) { toast(data?.detail || 'Erreur de correction', 'error'); currentStep = 3; updateSteps(); return; }
  currentExamId = data.exam_id;
  showResults(data, body);
}

function showResults(data, req) {
  currentStep = 5; updateSteps();
  document.getElementById('result-note').textContent = `${data.note_totale} / ${data.note_sur}`;
  document.getElementById('result-info').textContent = `${req.matiere} • ${req.niveau} • ${req.date_examen}`;
  document.getElementById('result-appreciation').innerHTML = `<b>Appréciation :</b> ${data.appreciation}`;
  renderReviewControls(data);
  if (data.alerte_anomalie) {
    const el = document.getElementById('result-anomaly');
    el.style.display = 'block'; el.innerHTML = `⚠️ <b>Alerte anomalie :</b> ${data.message_anomalie}`;
  }
  const container = document.getElementById('result-exercises');
  container.innerHTML = '';
  (data.exercices || []).forEach(ex => {
    container.innerHTML += `<div class="exercise-result"><div class="er-head"><span><b>Exercice ${ex.numero}</b></span><span class="pts" style="color:${ex.correct?'var(--success)':'var(--text)'}">${ex.points_obtenus} / ${ex.points_max}</span></div><div class="er-feedback">${ex.feedback}</div>${ex.erreurs_types?`<div class="er-errors">⚠ ${ex.erreurs_types}</div>`:''}</div>`;
  });
  toast(data.review_status === 'approved' ? 'Copie validée par l’enseignant.' : 'Proposition IA enregistrée : une validation humaine est requise.');
}

function reviewStatusLabel(status) {
  return {
    pending_review: 'À relire par l’enseignant',
    needs_revision: 'À corriger par l’enseignant',
    approved: 'Validée par l’enseignant',
  }[status || 'pending_review'] || 'À relire par l’enseignant';
}

function renderReviewControls(data) {
  const status = data.review_status || 'pending_review';
  const el = document.getElementById('result-review');
  if (status === 'approved') {
    const aiNote = data.ai_note_totale == null ? '—' : `${data.ai_note_totale} / ${data.note_sur}`;
    el.innerHTML = `<b>Décision de l’enseignant :</b> <span class="badge badge-success">${reviewStatusLabel(status)}</span><p class="text-sm text-muted mt-8">Proposition IA initiale : ${aiNote}. Validation : ${data.reviewed_at || '—'}.</p>`;
    return;
  }
  el.innerHTML = `<h4 style="margin-top:0">Validation humaine requise</h4>
    <p class="text-sm text-muted">La proposition IA n’est pas une note finale. Vérifiez chaque exercice avant de valider ou de renvoyer la copie en correction.</p>
    <div class="row"><div class="field"><label>Note finale (optionnelle)</label><input id="review-final-note" type="number" min="0" max="${data.note_sur || 20}" step="0.25" value="${data.note_totale ?? ''}"></div>
    <div class="field"><label>Commentaire de revue</label><input id="review-comment" maxlength="1000" placeholder="Ex. exercice 2 réévalué après relecture"></div></div>
    <div class="field"><label>Appréciation finale (optionnelle)</label><textarea id="review-final-appreciation" rows="2">${data.appreciation || ''}</textarea></div>
    <div style="display:flex;gap:10px"><button class="btn btn-primary" onclick="submitReview('approved')">Valider comme note finale</button><button class="btn btn-secondary" onclick="submitReview('needs_revision')">À corriger / revoir</button></div>`;
}

async function submitReview(status) {
  if (!currentExamId) return toast('Aucune copie à valider', 'error');
  const noteValue = document.getElementById('review-final-note')?.value;
  const payload = {
    status,
    comment: document.getElementById('review-comment')?.value || '',
    final_note: noteValue === '' || noteValue == null ? null : parseFloat(noteValue),
    final_appreciation: document.getElementById('review-final-appreciation')?.value || null,
  };
  const data = await api(`/api/grading/exams/${currentExamId}/review`, { method: 'POST', body: payload });
  if (!data || data.detail) return toast(data?.detail || 'Impossible d’enregistrer la revue', 'error');
  showResults(data, { matiere: data.matiere, niveau: data.niveau, date_examen: data.date_examen });
  if (status === 'approved') toast('Note finale validée : l’envoi du rapport est désormais autorisé.');
}

function resetCorrection() { exerciseCount = 0; navigate('corriger'); }

// ━━━ PDF & Email ━━━
async function downloadPDF() {
  if (!currentExamId) return toast('Aucune copie à télécharger', 'error');
  window.open(API + '/api/reports/pdf/' + currentExamId + '?token=' + token, '_blank');
  // Fallback: fetch with auth
  const res = await fetch(API + '/api/reports/pdf/' + currentExamId, { headers: { 'Authorization': 'Bearer ' + token } });
  if (res.ok) { const blob = await res.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `rapport_${currentExamId}.pdf`; a.click(); }
}

function downloadPDFById() {
  const id = document.getElementById('pdf-exam-id').value;
  if (!id) return toast('Entrez un ID', 'error');
  currentExamId = parseInt(id); downloadPDF();
}

function showEmailModal() { openModal('modal-email'); }

async function sendEmail() {
  const email = document.getElementById('me-email').value;
  const message = document.getElementById('me-message').value;
  if (!email || !currentExamId) return toast('Email et ID requis', 'error');
  const data = await api('/api/reports/email', { method: 'POST', body: { exam_id: currentExamId, to_email: email, message } });
  if (data?.message) { toast(data.message); closeModal('modal-email'); }
  else toast(data?.detail || 'Erreur d\'envoi', 'error');
}

function exportCSV() {
  const classe = document.getElementById('csv-classe').value;
  if (!classe) return toast('Indiquez une classe', 'error');
  window.open(API + '/api/reports/csv/classe/' + encodeURIComponent(classe), '_blank');
}

// ━━━ Élèves ━━━
async function loadStudents() {
  document.getElementById('students-grid').style.display = 'grid';
  document.getElementById('student-detail').style.display = 'none';
  const data = await api('/api/students/');
  const grid = document.getElementById('students-grid');
  grid.innerHTML = '';
  if (!data?.students?.length) { grid.innerHTML = '<div class="empty-state"><div class="icon">👥</div><p>Aucun élève</p><button class="btn btn-primary btn-sm mt-12" onclick="showAddStudent()">Ajouter un élève</button></div>'; return; }
  data.students.forEach(s => {
    grid.innerHTML += `<div class="student-card" onclick="showStudent(${s.id})">
<div class="sc-top"><div class="sc-avatar">${(s.prenom[0]+s.nom[0]).toUpperCase()}</div><div><div class="sc-name">${s.prenom} ${s.nom}</div><div class="sc-class">${s.classe}</div></div></div>
<div class="sc-stats"><span>📧 ${s.email||'—'}</span></div></div>`;
  });
}

function showAddStudent() {
  document.getElementById('modal-student-title').textContent = 'Ajouter un élève';
  ['ms-nom','ms-prenom','ms-classe','ms-email'].forEach(id => document.getElementById(id).value = '');
  openModal('modal-student');
}

async function saveStudent() {
  const body = { nom: document.getElementById('ms-nom').value, prenom: document.getElementById('ms-prenom').value, classe: document.getElementById('ms-classe').value, email: document.getElementById('ms-email').value };
  if (!body.nom || !body.prenom || !body.classe) return toast('Remplissez nom, prénom et classe', 'error');
  const data = await api('/api/students/', { method: 'POST', body });
  if (data?.id) { toast('Élève ajouté'); closeModal('modal-student'); loadStudents(); }
  else toast(data?.detail || 'Erreur', 'error');
}

async function showStudent(id) {
  document.getElementById('students-grid').style.display = 'none';
  document.getElementById('student-detail').style.display = 'block';
  const data = await api(`/api/students/${id}`);
  if (!data) return;
  document.getElementById('sd-name').textContent = `${data.prenom} ${data.nom}`;
  document.getElementById('sd-class').textContent = data.classe;
  document.getElementById('sd-avg').textContent = data.moyenne_generale > 0 ? data.moyenne_generale.toFixed(1) : '—';
  document.getElementById('sd-count').textContent = data.nb_exams;
  // Exams
  const exams = await api(`/api/students/${id}/exams`);
  const tbody = document.getElementById('sd-exams');
  tbody.innerHTML = '';
  (exams?.exams || []).forEach(e => {
    tbody.innerHTML += `<tr><td>${e.matiere}</td><td><span class="badge ${e.note_totale/e.note_sur>=0.5?'badge-success':'badge-danger'}">${e.note_totale}/${e.note_sur}</span></td><td>${e.date_examen||'—'}</td><td>${e.alerte_anomalie?'<span class="badge badge-danger">⚠</span>':'—'}</td></tr>`;
  });
  // Progression chart
  drawProgression(data.progression || {});
}

function drawProgression(progression) {
  const canvas = document.getElementById('chart-progression');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr;
  canvas.style.width = rect.width + 'px'; canvas.style.height = rect.height + 'px';
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height, pad = 40;
  ctx.clearRect(0, 0, W, H);
  const subjects = Object.keys(progression);
  if (!subjects.length) { ctx.fillStyle = '#94A3B8'; ctx.font = '14px DM Sans'; ctx.textAlign = 'center'; ctx.fillText('Pas encore de données', W/2, H/2); return; }
  const colors = ['#0EA5E9', '#6366F1', '#10B981', '#F59E0B', '#EF4444'];
  subjects.forEach((subj, si) => {
    const pts = progression[subj];
    if (pts.length < 2) return;
    const color = colors[si % colors.length];
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    pts.forEach((p, i) => {
      const x = pad + (i / (pts.length - 1)) * (W - pad * 2);
      const y = H - pad - (p.note_sur_20 / 20) * (H - pad * 2);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
    // Legend
    ctx.fillStyle = color; ctx.font = '11px DM Sans'; ctx.textAlign = 'left';
    ctx.fillText(subj, pad + si * 80, 16);
  });
}

function backToStudentList() { loadStudents(); }

// ━━━ Historique ━━━
async function loadHistory() {
  const data = await api('/api/exams?limit=100');
  const tbody = document.getElementById('history-table');
  tbody.innerHTML = '';
  let exams = data?.exams || [];
  const filterM = document.getElementById('filter-matiere').value.toLowerCase();
  if (filterM) exams = exams.filter(e => e.matiere.toLowerCase().includes(filterM));
  const filterC = document.getElementById('filter-classe').value;
  if (filterC) exams = exams.filter(e => e.classe === filterC);
  // Populate classe filter
  const classes = [...new Set((data?.exams || []).map(e => e.classe))];
  const sel = document.getElementById('filter-classe');
  const cur = sel.value;
  sel.innerHTML = '<option value="">Toutes les classes</option>';
  classes.forEach(c => sel.innerHTML += `<option value="${c}" ${c===cur?'selected':''}>${c}</option>`);
  exams.forEach(e => {
    const reviewClass = e.review_status === 'approved' ? 'badge-success' : e.review_status === 'needs_revision' ? 'badge-danger' : 'badge-warning';
    tbody.innerHTML += `<tr><td>${e.student_prenom} ${e.student_nom}</td><td>${e.classe}</td><td>${e.matiere}</td><td><span class="badge ${e.note_totale/e.note_sur>=0.5?'badge-success':'badge-danger'}">${e.note_totale}/${e.note_sur}</span></td><td><span class="badge ${reviewClass}">${reviewStatusLabel(e.review_status)}</span></td><td>${e.date_examen||'—'}</td><td>${e.alerte_anomalie?'<span class="badge badge-danger">⚠</span>':'—'}</td><td><button class="btn btn-sm btn-secondary" onclick="viewExam(${e.id})">Revoir</button></td></tr>`;
  });
  if (!exams.length) tbody.innerHTML = '<tr><td colspan="8" class="text-muted">Aucune copie</td></tr>';
}

async function viewExam(id) {
  const data = await api(`/api/grading/exams/${id}`);
  if (!data) return;
  currentExamId = id;
  navigate('corriger');
  showResults(data, { matiere: data.matiere, niveau: data.niveau, date_examen: data.date_examen });
}

// ━━━ Pilote : revue et calibration ━━━
async function loadPilot() {
  const [metrics, queue] = await Promise.all([
    api('/api/grading/pilot/metrics'),
    api('/api/grading/reviews/queue?status=pending_review&limit=50'),
  ]);
  if (!metrics || !queue) return;
  const review = metrics.review || {};
  const calibration = metrics.calibration || {};
  document.getElementById('pilot-pending').textContent = review.pending_review ?? 0;
  document.getElementById('pilot-revision').textContent = review.needs_revision ?? 0;
  document.getElementById('pilot-approved').textContent = review.approved ?? 0;
  document.getElementById('pilot-mae').textContent = calibration.mae_sur_20 == null ? '—' : calibration.mae_sur_20.toFixed(2);
  const tbody = document.getElementById('pilot-review-queue');
  tbody.innerHTML = '';
  (queue.exams || []).forEach(exam => {
    tbody.innerHTML += `<tr><td>${exam.student_prenom} ${exam.student_nom}</td><td>${exam.matiere}</td><td>${exam.ai_note_totale ?? exam.note_totale}/${exam.note_sur}</td><td><button class="btn btn-sm btn-secondary" onclick="viewExam(${exam.id})">Revoir</button></td></tr>`;
  });
  if (!(queue.exams || []).length) tbody.innerHTML = '<tr><td colspan="4" class="text-muted">Aucune copie en attente.</td></tr>';
  const summary = document.getElementById('pilot-quality-summary');
  if (!calibration.count) {
    summary.textContent = 'Ajoutez des références humaines pour calculer l’écart moyen, la part des notes à ±1 point et le biais du modèle.';
  } else {
    const one = ((calibration.within_one_point || 0) * 100).toFixed(0);
    const two = ((calibration.within_two_points || 0) * 100).toFixed(0);
    const bias = calibration.biais_moyen_sur_20 == null ? '—' : calibration.biais_moyen_sur_20.toFixed(2);
    summary.textContent = `${calibration.count} référence(s) : MAE ${calibration.mae_sur_20.toFixed(2)}/20 ; ${one}% des notes à ±1 point ; ${two}% à ±2 points ; biais moyen ${bias}/20.`;
  }
}

async function submitCalibration() {
  const examId = parseInt(document.getElementById('pilot-exam-id').value);
  const referenceNote = parseFloat(document.getElementById('pilot-reference-note').value);
  const referenceSur = parseFloat(document.getElementById('pilot-reference-sur').value || 20);
  if (!examId || Number.isNaN(referenceNote) || Number.isNaN(referenceSur)) {
    return toast('Indiquez l’ID de copie, la note humaine et son barème.', 'error');
  }
  const data = await api('/api/grading/pilot/calibration', {
    method: 'POST',
    body: {
      exam_id: examId,
      reference_note: referenceNote,
      reference_note_sur: referenceSur,
      reference_source: document.getElementById('pilot-reference-source').value || 'double_correction_humaine',
      notes: document.getElementById('pilot-reference-notes').value || '',
    },
  });
  if (!data || data.detail) return toast(data?.detail || 'Impossible d’enregistrer la référence', 'error');
  toast('Référence humaine enregistrée pour la calibration.');
  document.getElementById('pilot-reference-note').value = '';
  document.getElementById('pilot-reference-notes').value = '';
  loadPilot();
}

// ━━━ Init ━━━
if (token && currentUser) enterApp();
