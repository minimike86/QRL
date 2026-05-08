'use strict';

// ── Protocol ────────────────────────────────────────────────────────────────
const HEADER_SIZE = 9;
const MANIFEST_STREAM_ID = 255;

function unpackChunk(bytes) {
  if (bytes.length < HEADER_SIZE) return null;
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.length);
  return {
    streamId:    v.getUint8(0),
    sequence:    v.getUint32(1, false),
    totalChunks: v.getUint32(5, false),
    payload:     bytes.slice(HEADER_SIZE),
  };
}

// ── Decoder state ────────────────────────────────────────────────────────────
let manifest = null;
let received = new Map();   // sequence → Uint8Array payload
let expectedTotal = 0;
let complete = false;
let assembledData = null;   // final Uint8Array after reassembly

// Scan stats
let frameCount = 0;
let hitCount = 0;
let newCount = 0;
let dupCount = 0;
let receiveStartTime = null;

// Camera
let mediaStream = null;
let rafId = null;
let scanning = false;

// ── Camera setup ─────────────────────────────────────────────────────────────
async function startCamera() {
  try {
    await populateCameraSelect();

    const deviceId = document.getElementById('cameraSelect').value;
    const constraints = {
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
    };

    mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
    const video = document.getElementById('video');
    video.srcObject = mediaStream;
    await new Promise(res => { video.onloadedmetadata = res; });
    video.play();

    document.getElementById('videoWrap').classList.remove('hidden');
    document.getElementById('statsRow').classList.remove('hidden');
    document.getElementById('progressSection').classList.remove('hidden');
    document.getElementById('startBtn').classList.add('hidden');
    document.getElementById('stopBtn').classList.remove('hidden');
    document.getElementById('resetBtn').classList.remove('hidden');

    scanning = true;
    setStatus('Scanning for manifest QR…', 'warn');
    rafId = requestAnimationFrame(scanLoop);
  } catch (err) {
    setStatus('Camera error: ' + err.message, 'err');
  }
}

async function populateCameraSelect() {
  const sel = document.getElementById('cameraSelect');
  const prevId = sel.value;
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cameras = devices.filter(d => d.kind === 'videoinput');
  sel.innerHTML = '';
  cameras.forEach((cam, i) => {
    const opt = document.createElement('option');
    opt.value = cam.deviceId;
    opt.textContent = cam.label || `Camera ${i + 1}`;
    if (cam.deviceId === prevId) opt.selected = true;
    sel.appendChild(opt);
  });
  if (cameras.length > 1) sel.classList.remove('hidden');
}

function stopCamera() {
  scanning = false;
  if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  document.getElementById('video').srcObject = null;
  document.getElementById('videoWrap').classList.add('hidden');
  document.getElementById('startBtn').classList.remove('hidden');
  document.getElementById('stopBtn').classList.add('hidden');
  if (!complete) setStatus('Camera stopped.', 'idle');
}

async function switchCamera(deviceId) {
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  const video = document.getElementById('video');
  video.srcObject = null;
  const constraints = {
    video: deviceId
      ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
      : { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
  };
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
    video.srcObject = mediaStream;
    await new Promise(res => { video.onloadedmetadata = res; });
    video.play();
    setStatus('Camera switched. Scanning…', 'warn');
  } catch (err) {
    setStatus('Camera switch error: ' + err.message, 'err');
  }
}

// ── Scan loop ────────────────────────────────────────────────────────────────
function scanLoop() {
  if (!scanning) return;

  const video = document.getElementById('video');
  const canvas = document.getElementById('capCanvas');

  if (video.readyState === video.HAVE_ENOUGH_DATA) {
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    frameCount++;
    document.getElementById('sScans').textContent = frameCount;

    const code = jsQR(imgData.data, imgData.width, imgData.height, {
      inversionAttempts: 'attemptBoth',
    });

    const dot = document.getElementById('scanDot');
    if (code && code.binaryData && code.binaryData.length >= HEADER_SIZE) {
      hitCount++;
      document.getElementById('sHits').textContent = hitCount;
      dot.classList.add('active');
      document.getElementById('scanTxt').textContent = 'QR found';
      processChunk(new Uint8Array(code.binaryData));
    } else {
      dot.classList.remove('active');
      document.getElementById('scanTxt').textContent = 'scanning…';
    }
  }

  rafId = requestAnimationFrame(scanLoop);
}

// ── Chunk processing ─────────────────────────────────────────────────────────
function processChunk(bytes) {
  const chunk = unpackChunk(bytes);
  if (!chunk) return;

  if (chunk.streamId === MANIFEST_STREAM_ID) {
    if (!manifest) {
      try {
        manifest = JSON.parse(new TextDecoder().decode(chunk.payload));
        expectedTotal = manifest.total_chunks;
        showManifest(manifest);
        updateProgress();
      } catch (_) {}
    }
    return;
  }

  if (chunk.streamId !== 0) return;  // only single-stream supported

  // Require manifest before accepting data chunks
  if (!manifest) return;

  if (received.size === 0) {
    setStatus('Receiving chunks…', 'warn');
    document.getElementById('scanTxt').textContent = 'receiving…';
  }

  if (received.has(chunk.sequence)) {
    dupCount++;
    document.getElementById('sDups').textContent = dupCount;
    return;
  }

  if (!receiveStartTime) receiveStartTime = Date.now();
  received.set(chunk.sequence, chunk.payload);
  newCount++;
  document.getElementById('sNew').textContent = newCount;
  updateProgress();

  if (expectedTotal > 0 && received.size === expectedTotal) {
    finalise();
  }
}

// ── Reassembly ───────────────────────────────────────────────────────────────
function finalise() {
  complete = true;
  scanning = false;
  if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  document.getElementById('video').srcObject = null;

  // Sort sequences 0…N-1 and concatenate payloads
  const totalBytes = Array.from(received.values()).reduce((s, b) => s + b.length, 0);
  const combined = new Uint8Array(totalBytes);
  let offset = 0;
  for (let i = 0; i < expectedTotal; i++) {
    const part = received.get(i);
    if (!part) { setStatus(`Missing chunk ${i} — transfer incomplete.`, 'err'); return; }
    combined.set(part, offset);
    offset += part.length;
  }

  let data = combined;
  if (manifest?.compressed) {
    try { data = pako.ungzip(combined); }
    catch (e) { setStatus('Decompression failed: ' + e.message, 'err'); return; }
  }

  assembledData = data;

  document.getElementById('videoWrap').classList.add('hidden');
  document.getElementById('stopBtn').classList.add('hidden');
  document.getElementById('chunkMap').classList.add('hidden');
  document.getElementById('downloadBtn').classList.remove('hidden');
  setStatus(`✓ Transfer complete! ${fmtBytes(data.length)} ready.`, 'ok');

  // Auto-download
  downloadFile();
}

function downloadFile() {
  if (!assembledData) return;
  const filename = manifest?.filename || 'received_file';
  const blob = new Blob([assembledData]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showManifest(m) {
  const card = document.getElementById('manifestCard');
  const comp = m.compressed ? ` (gzip → ${fmtBytes(m.size)})` : '';
  card.innerHTML =
    `<div class="fname">${m.filename}</div>` +
    `<div>${fmtBytes(m.original_size)}${comp} &nbsp;·&nbsp; ${m.total_chunks} chunks × ${m.chunk_size} B</div>` +
    `<div style="color:#555">EC: ${m.error_correction} &nbsp;·&nbsp; ${m.is_directory ? 'folder (zip)' : 'file'} &nbsp;·&nbsp; ETA: <span id="rxEta">—</span></div>`;
  card.classList.remove('hidden');

  // Reveal chunk map and progress immediately so the user can see the empty grid
  document.getElementById('progressSection').classList.remove('hidden');
  document.getElementById('chunkMap').classList.remove('hidden');
  updateChunkMap();

  document.getElementById('scanTxt').textContent = 'waiting for data…';
  setStatus('Manifest received — waiting for sender to resume.', 'warn');
}

function calcRxEta() {
  if (!receiveStartTime || received.size === 0 || !expectedTotal) return '—';
  const elapsed = (Date.now() - receiveStartTime) / 1000;
  if (elapsed < 1) return '—';
  const rate = received.size / elapsed;
  const remaining = expectedTotal - received.size;
  if (remaining <= 0) return '0s';
  const secs = Math.round(remaining / rate);
  if (secs < 60) return secs + 's';
  return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
}

function updateProgress() {
  const n = received.size;
  const tot = expectedTotal || '?';
  const pct = expectedTotal ? Math.floor((n / expectedTotal) * 100) : 0;
  document.getElementById('pReceived').textContent = n;
  document.getElementById('pTotal').textContent = tot;
  document.getElementById('pPct').textContent = pct + '%';
  document.getElementById('progFill').style.width = pct + '%';
  const etaEl = document.getElementById('rxEta');
  if (etaEl) etaEl.textContent = calcRxEta();
  updateChunkMap();
}

function updateChunkMap() {
  if (!expectedTotal) return;
  const mapEl = document.getElementById('chunkMap');
  if (complete) { mapEl.classList.add('hidden'); return; }
  mapEl.classList.remove('hidden');

  const MAX_CELLS = 200;
  const cellSize = Math.ceil(expectedTotal / MAX_CELLS);
  const numCells = Math.ceil(expectedTotal / cellSize);
  const grid = document.getElementById('chunkGrid');
  grid.innerHTML = '';
  for (let i = 0; i < numCells; i++) {
    const start = i * cellSize;
    const end = Math.min(start + cellSize, expectedTotal);
    let recvd = 0;
    for (let j = start; j < end; j++) { if (received.has(j)) recvd++; }
    const cell = document.createElement('div');
    const full = recvd === end - start;
    cell.className = 'chunk-cell' + (full ? ' ok' : recvd > 0 ? ' partial' : '');
    grid.appendChild(cell);
  }

  const missing = [];
  for (let i = 0; i < expectedTotal; i++) { if (!received.has(i)) missing.push(i + 1); }
  const listEl = document.getElementById('missingList');
  if (missing.length === 0) {
    listEl.textContent = '';
  } else if (missing.length <= 100) {
    listEl.textContent = 'Missing: ' + missing.join(', ');
  } else {
    listEl.textContent = `Missing ${missing.length}: ${missing.slice(0, 80).join(', ')} … +${missing.length - 80} more`;
  }
}

function copyMissing() {
  const missing = [];
  for (let i = 0; i < expectedTotal; i++) { if (!received.has(i)) missing.push(i + 1); }
  if (!missing.length) { setStatus('No missing chunks!', 'ok'); return; }
  navigator.clipboard.writeText(missing.join(','))
    .then(() => setStatus(`Copied ${missing.length} missing chunk number(s) to clipboard.`, 'ok'))
    .catch(() => setStatus('Clipboard copy failed — copy the list manually.', 'warn'));
}

function setStatus(msg, cls = 'idle') {
  const el = document.getElementById('statusMsg');
  el.textContent = msg;
  el.className = 'status ' + cls;
}

function resetState() {
  stopCamera();
  manifest = null;
  received = new Map();
  expectedTotal = 0;
  complete = false;
  assembledData = null;
  frameCount = hitCount = newCount = dupCount = 0;
  receiveStartTime = null;
  ['sScans','sHits','sNew','sDups'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('manifestCard').classList.add('hidden');
  document.getElementById('downloadBtn').classList.add('hidden');
  document.getElementById('progressSection').classList.add('hidden');
  document.getElementById('chunkMap').classList.add('hidden');
  document.getElementById('statsRow').classList.add('hidden');
  updateProgress();
  setStatus('Reset. Press Start Camera to begin again.', 'idle');
  document.getElementById('startBtn').classList.remove('hidden');
  document.getElementById('stopBtn').classList.add('hidden');
}

function fmtBytes(n) {
  if (!n) return '0 B';
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(2) + ' MB';
}

document.getElementById('cameraSelect').addEventListener('change', function() {
  if (mediaStream) switchCamera(this.value);
});

populateCameraSelect();
