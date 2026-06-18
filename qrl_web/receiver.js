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

// ── Fountain decoding ────────────────────────────────────────────────────────
function seededRandom(seed) {
  let s = seed >>> 0;
  return () => { s = (Math.imul(1664525, s) + 1013904223) >>> 0; return s / 4294967296; };
}

function chooseDegree(rng, N) {
  if (N === 1) return 1;
  const r = rng();
  if (r < 0.50) return 1;
  if (r < 0.75) return Math.min(2, N);
  if (r < 0.90) return Math.min(3, N);
  return Math.min(N, 3 + Math.ceil(rng() * Math.min(N - 3, 5)));
}

function chooseIndices(rng, N, degree) {
  const idxs = new Set();
  while (idxs.size < Math.min(degree, N)) idxs.add(Math.floor(rng() * N));
  return [...idxs].sort((a, b) => a - b);
}

function xorInPlace(dst, src) {
  const len = Math.min(dst.length, src.length);
  for (let i = 0; i < len; i++) dst[i] ^= src[i];
}

function addFountainPacket(allIndices, xorPayload) {
  const payload = xorPayload.slice();
  const pending = [];
  for (const idx of allIndices) {
    const r = sourceRecovered.get(idx);
    if (r !== undefined) xorInPlace(payload, r);
    else pending.push(idx);
  }
  if (!pending.length) return;
  if (pending.length === 1) { recoverSourceChunk(pending[0], payload); return; }
  fountainPackets.push({ indices: pending, payload });
}

function recoverSourceChunk(startIdx, startPayload) {
  const queue = [{ idx: startIdx, payload: startPayload }];
  while (queue.length) {
    const { idx, payload } = queue.shift();
    if (sourceRecovered.has(idx)) continue;
    sourceRecovered.set(idx, payload);
    newCount++;
    document.getElementById('sNew').textContent = newCount;
    updateProgress();

    const remaining = [];
    for (const pkt of fountainPackets) {
      const i = pkt.indices.indexOf(idx);
      if (i === -1) { remaining.push(pkt); continue; }
      xorInPlace(pkt.payload, payload);
      pkt.indices.splice(i, 1);
      if (pkt.indices.length === 1) queue.push({ idx: pkt.indices[0], payload: pkt.payload });
      else if (pkt.indices.length > 1) remaining.push(pkt);
    }
    fountainPackets = remaining;
  }
  if (expectedTotal > 0 && sourceRecovered.size === expectedTotal) finalise();
}

// ── Decoder state ────────────────────────────────────────────────────────────
let manifest = null;
let received = new Map();
let expectedTotal = 0;
let complete = false;
let assembledData = null;

// Scan stats
let frameCount = 0;
let hitCount = 0;
let newCount = 0;
let dupCount = 0;
let receiveStartTime = null;

// Fountain decoding state
let fountainPackets = [];
let sourceRecovered = new Map();
let seenSeeds = new Set();

// Capture / stream state
let sourceMode = 'camera';  // 'camera' | 'screen'
let mediaStream = null;
let rafId = null;
let scanning = false;

// Crop state
let cropRect = null;       // { x, y, w, h } in native video coords, or null
let cropPicking = false;
let cropDragStart = null;  // native video point where drag started

// ── Source selection ──────────────────────────────────────────────────────────
function setSource(mode) {
  if (scanning) return;
  sourceMode = mode;
  const isScreen = mode === 'screen';
  document.getElementById('srcCamera').classList.toggle('active', !isScreen);
  document.getElementById('srcScreen').classList.toggle('active', isScreen);
  document.getElementById('cameraSelect').classList.toggle('hidden', isScreen);
  document.getElementById('screenNote').classList.toggle('hidden', !isScreen);
  document.getElementById('startBtn').textContent = isScreen ? 'Start Screen' : 'Start Camera';
}

function startCapture() {
  if (sourceMode === 'screen') startScreenCapture();
  else startCamera();
}

// ── Camera / Screen setup ─────────────────────────────────────────────────────
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
    _showCaptureUI();
    scanning = true;
    setStatus('Scanning for manifest QR…', 'warn');
    rafId = requestAnimationFrame(scanLoop);
  } catch (err) {
    setStatus('Camera error: ' + err.message, 'err');
  }
}

async function startScreenCapture() {
  try {
    mediaStream = await navigator.mediaDevices.getDisplayMedia({
      video: { cursor: 'never', frameRate: { ideal: 10, max: 30 } },
      audio: false,
    });
    const video = document.getElementById('video');
    video.srcObject = mediaStream;
    await new Promise(res => { video.onloadedmetadata = res; });
    video.play();
    // Stop scanning automatically if the user ends the share via the browser UI
    mediaStream.getVideoTracks()[0].addEventListener('ended', () => stopCamera());
    _showCaptureUI();
    scanning = true;
    setStatus('Screen captured — scanning for manifest QR…', 'warn');
    rafId = requestAnimationFrame(scanLoop);
  } catch (err) {
    if (err.name === 'NotAllowedError') {
      setStatus('Screen capture cancelled.', 'idle');
    } else {
      setStatus('Screen capture error: ' + err.message, 'err');
    }
  }
}

function _showCaptureUI() {
  document.getElementById('videoWrap').classList.remove('hidden');
  document.getElementById('cameraPlaceholder')?.classList.add('hidden');
  document.getElementById('statsRow').classList.remove('hidden');
  document.getElementById('progressSection').classList.remove('hidden');
  document.getElementById('startBtn').classList.add('hidden');
  document.getElementById('stopBtn').classList.remove('hidden');
  document.getElementById('resetBtn').classList.remove('hidden');
  document.getElementById('cropBtn').classList.remove('hidden');
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
  if (cropPicking) stopCropPick();
  document.getElementById('video').srcObject = null;
  document.getElementById('videoWrap').classList.add('hidden');
  document.getElementById('cameraPlaceholder')?.classList.remove('hidden');
  document.getElementById('startBtn').classList.remove('hidden');
  document.getElementById('stopBtn').classList.add('hidden');
  document.getElementById('cropBtn').classList.add('hidden');
  document.getElementById('clearCropBtn').classList.add('hidden');
  if (!complete) setStatus('Capture stopped.', 'idle');
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

// ── Crop region selection ─────────────────────────────────────────────────────
function getVideoPoint(e) {
  const video = document.getElementById('video');
  const rect = video.getBoundingClientRect();
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return { x: 0, y: 0 };

  let clientX, clientY;
  if (e.touches && e.touches.length > 0) {
    clientX = e.touches[0].clientX; clientY = e.touches[0].clientY;
  } else if (e.changedTouches && e.changedTouches.length > 0) {
    clientX = e.changedTouches[0].clientX; clientY = e.changedTouches[0].clientY;
  } else {
    clientX = e.clientX; clientY = e.clientY;
  }

  // object-fit: cover — the video is scaled so it fills the element, potentially clipping sides.
  // scale = max(display/native) so that the smaller dimension exactly fills.
  const scale = Math.max(rect.width / vw, rect.height / vh);
  const ox = (rect.width - vw * scale) / 2;   // negative when video is wider than element
  const oy = (rect.height - vh * scale) / 2;
  const x = Math.round((clientX - rect.left - ox) / scale);
  const y = Math.round((clientY - rect.top - oy) / scale);
  return { x: Math.max(0, Math.min(vw, x)), y: Math.max(0, Math.min(vh, y)) };
}

function _videoToDisplayCoords(vx, vy) {
  // Returns position in pixels relative to .video-wrap (the overlay parent).
  // Since the video is width:100% with no wrap padding it shares the wrap origin.
  const video = document.getElementById('video');
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  const dw = video.clientWidth;
  const dh = video.clientHeight;
  const scale = Math.max(dw / vw, dh / vh);
  const ox = (dw - vw * scale) / 2;
  const oy = (dh - vh * scale) / 2;
  return { x: vx * scale + ox, y: vy * scale + oy };
}

function _updateSelectionBox(start, cur) {
  const p1 = _videoToDisplayCoords(start.x, start.y);
  const p2 = _videoToDisplayCoords(cur.x, cur.y);
  const sel = document.getElementById('cropSelection');
  sel.style.left   = Math.min(p1.x, p2.x) + 'px';
  sel.style.top    = Math.min(p1.y, p2.y) + 'px';
  sel.style.width  = Math.abs(p2.x - p1.x) + 'px';
  sel.style.height = Math.abs(p2.y - p1.y) + 'px';
  sel.style.display = 'block';
}

function updateCropActiveDisplay() {
  if (!cropRect) return;
  const p1 = _videoToDisplayCoords(cropRect.x, cropRect.y);
  const p2 = _videoToDisplayCoords(cropRect.x + cropRect.w, cropRect.y + cropRect.h);
  const el = document.getElementById('cropActive');
  el.style.left   = p1.x + 'px';
  el.style.top    = p1.y + 'px';
  el.style.width  = (p2.x - p1.x) + 'px';
  el.style.height = (p2.y - p1.y) + 'px';
  el.style.display = 'block';
}

function startCropPick() {
  if (!scanning) return;
  cropPicking = true;
  cropRect = null;
  document.getElementById('cropActive').style.display = 'none';
  document.getElementById('clearCropBtn').classList.add('hidden');
  document.getElementById('cropBtn').textContent = 'Cancel';
  document.getElementById('cropOverlay').classList.add('picking');
  setStatus('Drag on the video to select a scan region.', 'warn');
}

function stopCropPick() {
  cropPicking = false;
  cropDragStart = null;
  document.getElementById('cropOverlay').classList.remove('picking');
  document.getElementById('cropSelection').style.display = 'none';
  document.getElementById('cropBtn').textContent = 'Crop Region';
}

function clearCrop() {
  stopCropPick();
  cropRect = null;
  document.getElementById('cropActive').style.display = 'none';
  document.getElementById('clearCropBtn').classList.add('hidden');
  setStatus('Crop cleared — scanning full frame.', 'warn');
}

function _finalizeCrop(start, end) {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const w = Math.abs(end.x - start.x);
  const h = Math.abs(end.y - start.y);
  stopCropPick();
  if (w < 10 || h < 10) {
    setStatus('Selection too small — try again.', 'warn');
    return;
  }
  cropRect = { x, y, w, h };
  document.getElementById('clearCropBtn').classList.remove('hidden');
  updateCropActiveDisplay();
  setStatus(`Crop: ${w}×${h} px — scanning region only.`, 'ok');
}

// ── Crop overlay event listeners ─────────────────────────────────────────────
(function attachCropEvents() {
  const overlay = document.getElementById('cropOverlay');

  overlay.addEventListener('mousedown', e => {
    if (!cropPicking) return;
    e.preventDefault();
    cropDragStart = getVideoPoint(e);
  });

  overlay.addEventListener('mousemove', e => {
    if (!cropPicking || !cropDragStart) return;
    e.preventDefault();
    _updateSelectionBox(cropDragStart, getVideoPoint(e));
  });

  overlay.addEventListener('mouseup', e => {
    if (!cropPicking || !cropDragStart) return;
    e.preventDefault();
    _finalizeCrop(cropDragStart, getVideoPoint(e));
  });

  overlay.addEventListener('touchstart', e => {
    if (!cropPicking) return;
    e.preventDefault();
    cropDragStart = getVideoPoint(e);
  }, { passive: false });

  overlay.addEventListener('touchmove', e => {
    if (!cropPicking || !cropDragStart) return;
    e.preventDefault();
    _updateSelectionBox(cropDragStart, getVideoPoint(e));
  }, { passive: false });

  overlay.addEventListener('touchend', e => {
    if (!cropPicking || !cropDragStart) return;
    e.preventDefault();
    _finalizeCrop(cropDragStart, getVideoPoint(e));
  }, { passive: false });
})();

window.addEventListener('resize', () => { if (cropRect) updateCropActiveDisplay(); });

// ── Scan loop ────────────────────────────────────────────────────────────────
function scanLoop() {
  if (!scanning) return;

  const video = document.getElementById('video');
  const canvas = document.getElementById('capCanvas');

  if (video.readyState === video.HAVE_ENOUGH_DATA && video.videoWidth > 0) {
    const ctx = canvas.getContext('2d');

    if (cropRect) {
      canvas.width  = cropRect.w;
      canvas.height = cropRect.h;
      ctx.drawImage(video, cropRect.x, cropRect.y, cropRect.w, cropRect.h, 0, 0, cropRect.w, cropRect.h);
    } else {
      canvas.width  = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0);
    }

    const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    frameCount++;
    document.getElementById('sScans').textContent = frameCount;

    const code = jsQR(imgData.data, imgData.width, imgData.height, {
      inversionAttempts: 'attemptBoth',
    });

    const dot = document.getElementById('scanDot');
    if (code && code.data && code.data.length >= HEADER_SIZE) {
      const bytes = new Uint8Array(code.data.length);
      for (let k = 0; k < code.data.length; k++) bytes[k] = code.data.charCodeAt(k) & 0xff;
      hitCount++;
      document.getElementById('sHits').textContent = hitCount;
      dot.classList.add('active');
      document.getElementById('scanTxt').textContent = 'QR found';
      processChunk(bytes);
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
      } catch (e) {
        console.error('[QRL] Manifest processing error:', e);
        setStatus('Manifest error: ' + e.message, 'err');
      }
    }
    return;
  }

  if (!manifest) return;

  // ── Fountain packet (stream 2) ────────────────────────────────────────────
  if (chunk.streamId === 2) {
    if (complete) return;
    const seed = chunk.sequence;
    if (seenSeeds.has(seed)) {
      dupCount++;
      document.getElementById('sDups').textContent = dupCount;
      return;
    }
    seenSeeds.add(seed);
    if (sourceRecovered.size === 0) {
      setStatus('Receiving fountain packets…', 'warn');
      document.getElementById('scanTxt').textContent = 'receiving…';
    }
    if (!receiveStartTime) receiveStartTime = Date.now();
    const N = chunk.totalChunks;
    const rng = seededRandom(seed);
    const degree = chooseDegree(rng, N);
    const indices = chooseIndices(rng, N, degree);
    addFountainPacket(indices, chunk.payload.slice());
    return;
  }

  if (chunk.streamId !== 0) return;

  // ── Sequential packet (stream 0) ─────────────────────────────────────────
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
  if (cropPicking) stopCropPick();
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  document.getElementById('video').srcObject = null;
  document.getElementById('videoWrap').classList.add('hidden');
  document.getElementById('cameraPlaceholder')?.classList.remove('hidden');
  document.getElementById('cropBtn').classList.add('hidden');
  document.getElementById('clearCropBtn').classList.add('hidden');
  document.getElementById('cropActive').style.display = 'none';

  let combined;
  if (manifest?.fountain) {
    const totalBytes = manifest.size;
    combined = new Uint8Array(totalBytes);
    let offset = 0;
    for (let i = 0; i < expectedTotal; i++) {
      const part = sourceRecovered.get(i);
      if (!part) { setStatus(`Source chunk ${i} not recovered.`, 'err'); return; }
      const actualSize = Math.min(manifest.chunk_size, totalBytes - offset);
      combined.set(part.subarray(0, actualSize), offset);
      offset += actualSize;
    }
  } else {
    const totalBytes = Array.from(received.values()).reduce((s, b) => s + b.length, 0);
    combined = new Uint8Array(totalBytes);
    let offset = 0;
    for (let i = 0; i < expectedTotal; i++) {
      const part = received.get(i);
      if (!part) { setStatus(`Missing chunk ${i} — transfer incomplete.`, 'err'); return; }
      combined.set(part, offset);
      offset += part.length;
    }
  }

  let data = combined;
  if (manifest?.compressed) {
    try { data = pako.ungzip(combined); }
    catch (e) { setStatus('Decompression failed: ' + e.message, 'err'); return; }
  }

  assembledData = data;

  document.getElementById('stopBtn').classList.add('hidden');
  document.getElementById('chunkMap').classList.add('hidden');
  document.getElementById('downloadBtn').classList.remove('hidden');
  setStatus(`✓ Transfer complete! ${fmtBytes(data.length)} ready.`, 'ok');

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

  document.getElementById('progressSection').classList.remove('hidden');
  document.getElementById('chunkMap').classList.remove('hidden');
  updateChunkMap();

  document.getElementById('scanTxt').textContent = 'waiting for data…';
  setStatus('Manifest received — waiting for sender to resume.', 'warn');
}

function chunkReceived(i) {
  return manifest?.fountain ? sourceRecovered.has(i) : received.has(i);
}

function recoveredCount() {
  return manifest?.fountain ? sourceRecovered.size : received.size;
}

function calcRxEta() {
  if (!receiveStartTime || !expectedTotal) return '—';
  const n = recoveredCount();
  if (n === 0) return '—';
  const elapsed = (Date.now() - receiveStartTime) / 1000;
  if (elapsed < 1) return '—';
  const rate = n / elapsed;
  const remaining = expectedTotal - n;
  if (remaining <= 0) return '0s';
  const secs = Math.round(remaining / rate);
  if (secs < 60) return secs + 's';
  return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
}

function updateProgress() {
  const n = recoveredCount();
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
    for (let j = start; j < end; j++) { if (chunkReceived(j)) recvd++; }
    const cell = document.createElement('div');
    const full = recvd === end - start;
    cell.className = 'chunk-cell' + (full ? ' ok' : recvd > 0 ? ' partial' : '');
    grid.appendChild(cell);
  }

  const missing = [];
  for (let i = 0; i < expectedTotal; i++) { if (!chunkReceived(i)) missing.push(i + 1); }
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
  for (let i = 0; i < expectedTotal; i++) { if (!chunkReceived(i)) missing.push(i + 1); }
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
  stopCamera();  // also calls stopCropPick if picking is active
  cropRect = null;
  document.getElementById('cropActive').style.display = 'none';
  document.getElementById('clearCropBtn').classList.add('hidden');
  manifest = null;
  received = new Map();
  expectedTotal = 0;
  complete = false;
  assembledData = null;
  frameCount = hitCount = newCount = dupCount = 0;
  receiveStartTime = null;
  fountainPackets = [];
  sourceRecovered = new Map();
  seenSeeds = new Set();
  ['sScans','sHits','sNew','sDups'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('manifestCard').classList.add('hidden');
  document.getElementById('downloadBtn').classList.add('hidden');
  document.getElementById('progressSection').classList.add('hidden');
  document.getElementById('chunkMap').classList.add('hidden');
  document.getElementById('statsRow').classList.add('hidden');
  updateProgress();
  setStatus('Reset. Press Start to begin again.', 'idle');
  document.getElementById('startBtn').classList.remove('hidden');
  document.getElementById('stopBtn').classList.add('hidden');
}

function fmtBytes(n) {
  if (!n) return '0 B';
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(2) + ' MB';
}

// ── Initialisation ────────────────────────────────────────────────────────────
document.getElementById('cameraSelect').addEventListener('change', function() {
  if (mediaStream && sourceMode === 'camera') switchCamera(this.value);
});

// Disable Screen tab if getDisplayMedia is not available (older browsers, some mobile)
if (!navigator.mediaDevices?.getDisplayMedia) {
  const btn = document.getElementById('srcScreen');
  btn.disabled = true;
  btn.title = 'Screen capture is not supported in this browser';
}

populateCameraSelect();
