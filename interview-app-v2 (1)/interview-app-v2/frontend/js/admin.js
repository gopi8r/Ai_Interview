/**
 * Admin dashboard logic.
 * - Login re-uses the same /api/auth/login endpoint as candidates, but
 *   rejects the token if role !== 'admin'.
 * - All data calls go to /api/admin/* which are protected by
 *   get_current_admin on the backend (403 for non-admin tokens).
 * - PDF download is fetched with the Authorization header (can't use a plain
 *   <a href> since that can't attach a JWT), then opened via a Blob URL.
 */

const API_BASE = "http://127.0.0.1:8000";

const screens = {
  login: document.getElementById('screen-admin-login'),
  dashboard: document.getElementById('screen-dashboard'),
};

function showScreen(name) {
  Object.values(screens).forEach((s) => s.classList.remove('active'));
  screens[name].classList.add('active');
}

let adminToken = localStorage.getItem('adminToken') || null;
let currentCandidates = [];
let activeSessionId = null;

function authHeaders(extra = {}) {
  return { Authorization: `Bearer ${adminToken}`, ...extra };
}

// ---------------- Login ----------------
async function handleAdminLogin() {
  const email = document.getElementById('adminEmail').value.trim();
  const password = document.getElementById('adminPassword').value;
  const errorEl = document.getElementById('adminAuthError');
  errorEl.classList.add('d-none');

  if (!email || !password) {
    errorEl.textContent = 'Please enter email and password.';
    errorEl.classList.remove('d-none');
    return;
  }

  const body = new URLSearchParams();
  body.append('username', email);
  body.append('password', password);

  try {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json();
    if (data.role !== 'admin') {
      throw new Error('This account is not an admin. Use the candidate site instead.');
    }
    adminToken = data.access_token;
    localStorage.setItem('adminToken', adminToken);
    showScreen('dashboard');
    loadDashboard();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove('d-none');
  }
}

function adminLogout() {
  adminToken = null;
  localStorage.removeItem('adminToken');
  showScreen('login');
}

// ---------------- Dashboard data ----------------
async function loadDashboard() {
  await Promise.all([loadSettings(), loadCandidates()]);
}

async function loadSettings() {
  try {
    const res = await fetch(`${API_BASE}/api/admin/settings`, { headers: authHeaders() });
    if (!res.ok) throw new Error('Could not load settings');
    const data = await res.json();
    document.getElementById('questionLimitInput').value = data.question_limit;
  } catch (err) {
    console.error(err);
  }
}

async function saveSettings() {
  const value = parseInt(document.getElementById('questionLimitInput').value, 10);
  if (isNaN(value) || value < 1 || value > 20) {
    alert('Please enter a question limit between 1 and 20.');
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/admin/settings`, {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ question_limit: value }),
    });
    if (!res.ok) throw new Error('Could not save settings');
    const msg = document.getElementById('settingsSavedMsg');
    msg.classList.remove('d-none');
    setTimeout(() => msg.classList.add('d-none'), 2000);
  } catch (err) {
    alert(err.message);
  }
}

async function loadCandidates() {
  try {
    const res = await fetch(`${API_BASE}/api/admin/candidates`, { headers: authHeaders() });
    if (!res.ok) throw new Error('Could not load candidates');
    currentCandidates = await res.json();
    renderStats(currentCandidates);
    renderCandidatesTable(currentCandidates);
  } catch (err) {
    alert(err.message);
  }
}

function renderStats(candidates) {
  document.getElementById('statTotal').textContent = candidates.length;

  const scored = candidates.filter((c) => c.overall_score !== null);
  const avg = scored.length
    ? (scored.reduce((sum, c) => sum + c.overall_score, 0) / scored.length).toFixed(1)
    : '--';
  document.getElementById('statAvgScore').textContent = avg;

  const hires = candidates.filter((c) => c.verdict === 'Hire' || c.verdict === 'Strong Hire').length;
  document.getElementById('statHires').textContent = hires;
}

function verdictBadgeClass(verdict) {
  switch (verdict) {
    case 'Strong Hire': return 'verdict-strong-hire';
    case 'Hire': return 'verdict-hire';
    case 'Borderline': return 'verdict-borderline';
    case 'No Hire': return 'verdict-no-hire';
    default: return 'verdict-pending';
  }
}

function renderCandidatesTable(candidates) {
  const tbody = document.getElementById('candidatesTableBody');
  const emptyMsg = document.getElementById('noCandidatesMsg');
  tbody.innerHTML = '';

  if (candidates.length === 0) {
    emptyMsg.classList.remove('d-none');
    return;
  }
  emptyMsg.classList.add('d-none');

  candidates.forEach((c) => {
    const skillsHtml = (c.skills || []).map((s) => `<span class="skills-chip">${escapeHtml(s)}</span>`).join(' ');
    const verdict = c.verdict || 'Pending';
    const overall = c.overall_score !== null ? c.overall_score.toFixed(1) : '—';
    const date = c.completed_at
      ? new Date(c.completed_at).toLocaleDateString()
      : new Date(c.started_at).toLocaleDateString() + ' (in progress)';

    const row = document.createElement('tr');
    row.innerHTML = `
      <td>
        <div class="fw-semibold">${escapeHtml(c.candidate_name)}</div>
        <div class="text-muted small">${escapeHtml(c.candidate_email)}</div>
      </td>
      <td>${c.experience_years ?? '—'} yrs</td>
      <td>${skillsHtml}</td>
      <td class="fw-semibold">${overall}</td>
      <td><span class="verdict-badge ${verdictBadgeClass(verdict)}">${verdict}</span></td>
      <td class="text-muted small">${date}</td>
      <td><button class="btn btn-outline-brand btn-sm" onclick="viewDetail(${c.session_id})" ${c.overall_score === null ? 'disabled' : ''}>View</button></td>
    `;
    tbody.appendChild(row);
  });
}

// ---------------- Candidate detail ----------------
async function viewDetail(sessionId) {
  try {
    const res = await fetch(`${API_BASE}/api/admin/candidates/${sessionId}`, { headers: authHeaders() });
    if (!res.ok) throw new Error('Could not load candidate detail');
    const data = await res.json();
    renderDetail(data);
  } catch (err) {
    alert(err.message);
  }
}

function renderDetail(data) {
  activeSessionId = data.session_id;
  document.getElementById('detailSection').classList.remove('d-none');
  document.getElementById('detailName').textContent = data.candidate_name;
  document.getElementById('detailEmail').textContent = data.candidate_email;
  document.getElementById('detailOverall').textContent = data.overall_score?.toFixed(1) ?? '--';
  document.getElementById('detailTechnical').textContent = data.avg_technical_score?.toFixed(1) ?? '--';
  document.getElementById('detailCommunication').textContent = data.avg_communication_score?.toFixed(1) ?? '--';

  const container = document.getElementById('detailAnswers');
  container.innerHTML = '';
  data.answers.forEach((a, idx) => {
    const div = document.createElement('div');
    div.className = 'qa-block';
    div.innerHTML = `
      <div class="fw-semibold">Q${idx + 1}. ${escapeHtml(a.question_text)}</div>
      <div class="qa-scores">
        Technical: ${a.technical_score}/10 · Communication: ${a.communication_score}/10
        · ${a.words_per_minute} wpm · ${a.time_taken_seconds}s
      </div>
      <div>${escapeHtml(a.feedback)}</div>
      ${a.missed_concepts.length ? `<div class="qa-missed">Missed: ${escapeHtml(a.missed_concepts.join('; '))}</div>` : ''}
      <div class="text-muted small mt-2"><i>Transcript:</i> "${escapeHtml(a.transcript)}"</div>
    `;
    container.appendChild(div);
  });

  document.getElementById('detailSection').scrollIntoView({ behavior: 'smooth' });
}

function closeDetail() {
  document.getElementById('detailSection').classList.add('d-none');
  activeSessionId = null;
}

document.getElementById('btnDownloadReport').addEventListener('click', async () => {
  if (!activeSessionId) return;
  try {
    const res = await fetch(`${API_BASE}/api/admin/candidates/${activeSessionId}/report`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error('Could not generate report');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `interview-report-${activeSessionId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    alert(err.message);
  }
});

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

window.addEventListener('DOMContentLoaded', () => {
  if (adminToken) {
    showScreen('dashboard');
    loadDashboard();
  } else {
    showScreen('login');
  }
});
