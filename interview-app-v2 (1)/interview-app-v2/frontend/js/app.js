/**
 * AI Interview Helper - Candidate frontend logic
 * ------------------------------------------------------------
 * - Registration collects skills + experience, used server-side to generate
 *   tailored questions via Gemini.
 * - Text-to-Speech: browser SpeechSynthesis API reads each question aloud.
 * - Speech capture: MediaRecorder records the candidate's mic audio as a
 *   webm blob, uploaded to the backend where Whisper transcribes it.
 * - IMPORTANT: candidates never see scores or a PDF here by design - once
 *   the interview is submitted, they just get a thank-you screen. Results
 *   are only visible to admins via admin.html.
 * ------------------------------------------------------------
 */

const API_BASE = "http://127.0.0.1:8000"; // change if backend runs elsewhere

const screens = {
  home: document.getElementById('screen-home'),
  auth: document.getElementById('screen-auth'),
  start: document.getElementById('screen-start'),
  interview: document.getElementById('screen-interview'),
  loading: document.getElementById('screen-loading'),
  done: document.getElementById('screen-done'),
};

function showScreen(name) {
  Object.values(screens).forEach((s) => s.classList.remove('active'));
  screens[name].classList.add('active');
}

// ---------------- Avatar state management ----------------
// Replaces showing the raw Whisper transcript to the candidate - instead we
// show an animated avatar reflecting what's happening (speaking the question,
// listening, thinking/transcribing, done).
const AVATAR_STATES = {
  idle:      { emoji: '🙂', caption: 'Get ready...' },
  speaking:  { emoji: '🗣️', caption: 'Reading question aloud...' },
  ready:     { emoji: '🎙️', caption: 'Click "Start Answer" when ready' },
  listening: { emoji: '👂', caption: 'Listening... speak your answer now' },
  thinking:  { emoji: '🤔', caption: 'Processing your answer...' },
  done:      { emoji: '✅', caption: 'Answer captured!' },
};

function setAvatarState(state) {
  const cfg = AVATAR_STATES[state] || AVATAR_STATES.idle;
  const circle = document.getElementById('avatarCircle');
  circle.className = 'avatar-circle state-' + state;
  document.getElementById('avatarEmoji').textContent = cfg.emoji;
  document.getElementById('micStatus').textContent = cfg.caption;
}

// ---------------- Auth state ----------------
let authToken = localStorage.getItem('authToken') || null;
let currentUserName = localStorage.getItem('userName') || '';

function switchAuthTab(tab) {
  document.getElementById('tab-login').classList.toggle('active', tab === 'login');
  document.getElementById('tab-register').classList.toggle('active', tab === 'register');
  document.getElementById('form-login').classList.toggle('d-none', tab !== 'login');
  document.getElementById('form-register').classList.toggle('d-none', tab !== 'register');
  hideAuthError();
}

function showAuthError(msg) {
  const el = document.getElementById('authError');
  el.textContent = msg;
  el.classList.remove('d-none');
}
function hideAuthError() {
  document.getElementById('authError').classList.add('d-none');
}

async function handleRegister() {
  const name = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;
  const experience_years = parseInt(document.getElementById('regExperience').value, 10);
  const skillsRaw = document.getElementById('regSkills').value.trim();
  const skills = skillsRaw ? skillsRaw.split(',').map((s) => s.trim()).filter(Boolean) : [];

  if (!name || !email || !password || isNaN(experience_years) || skills.length === 0) {
    return showAuthError('Please fill all fields, including at least one skill.');
  }

  try {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password, experience_years, skills }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Registration failed');
    }
    await loginRequest(email, password);
  } catch (err) {
    showAuthError(err.message);
  }
}

async function handleLogin() {
  const email = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;
  if (!email || !password) return showAuthError('Please enter email and password.');
  try {
    await loginRequest(email, password);
  } catch (err) {
    showAuthError(err.message);
  }
}

async function loginRequest(email, password) {
  const body = new URLSearchParams();
  body.append('username', email);
  body.append('password', password);

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

  if (data.role !== 'candidate') {
    throw new Error('This is an admin account. Please use the admin dashboard instead.');
  }

  authToken = data.access_token;
  currentUserName = data.name;
  localStorage.setItem('authToken', authToken);
  localStorage.setItem('userName', currentUserName);

  document.getElementById('welcomeName').textContent = currentUserName;
  showScreen('start');
}

function logout() {
  authToken = null;
  localStorage.removeItem('authToken');
  localStorage.removeItem('userName');
  showScreen('home');
}

function authHeaders(extra = {}) {
  return { Authorization: `Bearer ${authToken}`, ...extra };
}

// ---------------- Interview state ----------------
let questions = [];
let currentIndex = 0;
let sessionId = null;

let mediaRecorder = null;
let audioChunks = [];
let recordingStartTime = null;
let timerInterval = null;
let timeRemaining = 0;
let recording = false;

async function startInterview() {
  try {
    const res = await fetch(`${API_BASE}/api/interview/session/start`, {
      method: 'POST',
      headers: authHeaders(),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Could not start session');
    }
    const data = await res.json();
    sessionId = data.session_id;
    questions = data.questions;
    currentIndex = 0;
    showScreen('interview');
    renderQuestion();
  } catch (err) {
    alert(err.message);
  }
}

function renderQuestion() {
  const q = questions[currentIndex];
  document.getElementById('qProgress').textContent = `Question ${currentIndex + 1} / ${questions.length}`;
  document.getElementById('qTopic').textContent = q.topic;
  document.getElementById('qText').textContent = q.question_text;
  document.getElementById('btnRecord').disabled = true;
  document.getElementById('btnRecord').textContent = '🎙️ Start Answer';
  document.getElementById('btnNext').disabled = true;
  setAvatarState('speaking');

  timeRemaining = q.time_limit_seconds;
  updateTimerDisplay();

  speakCurrentQuestion();
}

function speakCurrentQuestion() {
  const q = questions[currentIndex];
  window.speechSynthesis.cancel();
  setAvatarState('speaking');
  const utterance = new SpeechSynthesisUtterance(q.question_text);
  utterance.rate = 1;
  utterance.lang = 'en-US';
  utterance.onend = () => {
    setAvatarState('ready');
    document.getElementById('btnRecord').disabled = false;
  };
  window.speechSynthesis.speak(utterance);
}

function updateTimerDisplay() {
  const m = String(Math.floor(timeRemaining / 60)).padStart(2, '0');
  const s = String(timeRemaining % 60).padStart(2, '0');
  document.getElementById('timer').textContent = `${m}:${s}`;
}

function startTimer() {
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    timeRemaining--;
    updateTimerDisplay();
    if (timeRemaining <= 0) {
      clearInterval(timerInterval);
      stopRecording(true);
    }
  }, 1000);
}

async function toggleRecording() {
  if (!recording) {
    await startRecording();
  } else {
    stopRecording(false);
  }
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
    mediaRecorder.start();

    recording = true;
    recordingStartTime = Date.now();
    startTimer();

    setAvatarState('listening');
    document.getElementById('btnRecord').textContent = '⏹ Stop Answer';
    document.getElementById('btnNext').disabled = false;
  } catch (err) {
    alert('Microphone access is required to record your answer: ' + err.message);
  }
}

// Returns a Promise that resolves once MediaRecorder has fully flushed its
// last chunk - prevents uploading a corrupt/incomplete webm file.
function stopRecordingAndWait() {
  return new Promise((resolve) => {
    if (!recording || !mediaRecorder) {
      resolve();
      return;
    }
    recording = false;
    mediaRecorder.onstop = () => {
      mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      resolve();
    };
    mediaRecorder.stop();
  });
}

function stopRecording(autoSubmitted) {
  clearInterval(timerInterval);
  document.getElementById('btnRecord').disabled = true;
  setAvatarState('thinking');

  if (autoSubmitted) {
    submitCurrentAnswer();
  }
}

async function submitCurrentAnswer() {
  await stopRecordingAndWait();
  clearInterval(timerInterval);

  const q = questions[currentIndex];
  const timeTaken = Math.min(
    q.time_limit_seconds,
    Math.round((Date.now() - recordingStartTime) / 1000)
  );

  setAvatarState('thinking');
  document.getElementById('btnNext').disabled = true;
  document.getElementById('btnRecord').disabled = true;

  try {
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('question_index', q.question_index);
    formData.append('time_taken_seconds', timeTaken);
    formData.append('audio', audioBlob, 'answer.webm');

    const res = await fetch(`${API_BASE}/api/interview/session/${sessionId}/answer`, {
      method: 'POST',
      headers: authHeaders(),
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to upload answer');
    // Intentionally not reading/displaying data.transcript here - candidates
    // never see the raw Whisper transcription, only the avatar feedback.
    await res.json();
    setAvatarState('done');

    currentIndex++;
    if (currentIndex < questions.length) {
      setTimeout(() => renderQuestion(), 800);
    } else {
      finishInterview();
    }
  } catch (err) {
    alert(err.message);
    document.getElementById('btnNext').disabled = false;
  }
}

async function finishInterview() {
  showScreen('loading');
  try {
    const res = await fetch(`${API_BASE}/api/interview/session/${sessionId}/evaluate`, {
      method: 'POST',
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error('Submission failed');
    // Intentionally ignore the response body content beyond a success check -
    // candidates never see scores here.
    await res.json();
    showScreen('done');
  } catch (err) {
    alert(err.message);
    showScreen('start');
  }
}

function restart() {
  sessionId = null;
  questions = [];
  showScreen('home');
}

window.addEventListener('DOMContentLoaded', () => {
  if (authToken) {
    document.getElementById('welcomeName').textContent = currentUserName;
    showScreen('start');
  } else {
    showScreen('home');
  }
});
