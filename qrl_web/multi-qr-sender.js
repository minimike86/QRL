'use strict';

// ── Protocol ─────────────────────────────────────────────────────────────────
const HEADER_SIZE = 9;
const MANIFEST_STREAM_ID = 255;

function packHeader(streamId, sequence, totalChunks) {
  const buf = new ArrayBuffer(9);
  const v = new DataView(buf);
  v.setUint8(0, streamId);
  v.setUint32(1, sequence, false);
  v.setUint32(5, totalChunks, false);
  return new Uint8Array(buf);
}

function buildManifestChunk(manifest) {
  const jsonBytes = new TextEncoder().encode(JSON.stringify(manifest));
  const hdr = packHeader(MANIFEST_STREAM_ID, 0, 1);
  const out = new Uint8Array(hdr.length + jsonBytes.length);
  out.set(hdr); out.set(jsonBytes, hdr.length);
  return out;
}

function concat2(a, b) {
  const out = new Uint8Array(a.length + b.length);
  out.set(a); out.set(b, a.length);
  return out;
}

function toByteString(u8) {
  let s = '';
  for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
  return s;
}

// ── Fountain coding ───────────────────────────────────────────────────────────
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

function buildFountainPacket(seed, chunks) {
  const N = chunks.length;
  const rng = seededRandom(seed);
  const idxs = chooseIndices(rng, N, chooseDegree(rng, N));
  const size = chunks[0].length;
  const payload = new Uint8Array(size);
  for (const i of idxs) { const src = chunks[i]; for (let j = 0; j < size; j++) payload[j] ^= src[j]; }
  const hdr = packHeader(2, seed, N);
  const out = new Uint8Array(HEADER_SIZE + size); out.set(hdr); out.set(payload, HEADER_SIZE);
  return out;
}

// ── State ─────────────────────────────────────────────────────────────────────
let framedChunks = [];
let paddedChunks = [];
let manifestBytes = null;
let isFountain = true;

let isRunning = false;
let isPaused = false;
let isManifestPhase = true;
let timerId = null;
let rendering = false;    // guard against overlapping async renders
let seqPos = 0;           // sequential: next chunk index (0-based)
let cycleCount = 0;
let fountainSeed = 0;     // total packets dispatched across all slots
let repeatCount = 0;
let frameCount = 0;
let fpsAvg = 0;
let lastFrameTs = 0;

let gridCols = 2;
let gridRows = 2;
let canvases = [];        // DOM canvas elements, one per grid slot

let lastRawData = null;
let lastFilename = null;
let lastIsDirectory = false;

function numQR() { return gridCols * gridRows; }

// ── Grid management ───────────────────────────────────────────────────────────
function buildGrid() {
  const count = numQR();
  const size = canvasSize();
  const container = document.getElementById('qrGrid');
  container.style.gridTemplateColumns = `repeat(${gridCols}, auto)`;

  while (canvases.length > count) canvases.pop().remove();
  while (canvases.length < count) {
    const c = document.createElement('canvas');
    c.className = 'qr-cell';
    container.appendChild(c);
    canvases.push(c);
  }
  resizeCanvases(size);
}

function resizeCanvases(size) {
  for (const c of canvases) {
    if (c.width !== size || c.height !== size) { c.width = size; c.height = size; }
    c.style.width = size + 'px';
    c.style.height = size + 'px';
  }
}

function canvasSize() { return Math.max(80, parseInt(document.getElementById('qrSize').value) || 300); }

// ── File reading ──────────────────────────────────────────────────────────────
document.getElementById('fileInput').addEventListener('change', async e => {
  const f = e.target.files[0];
  if (f) await handleFile(f);
  e.target.value = '';
});

document.getElementById('folderInput').addEventListener('change', async e => {
  const files = Array.from(e.target.files);
  if (files.length) await handleFolder(files);
  e.target.value = '';
});

async function handleFile(file) {
  setStatus('Reading…');
  try {
    const raw = new Uint8Array(await file.arrayBuffer());
    lastRawData = raw; lastFilename = file.name; lastIsDirectory = false;
    await prepare(raw, file.name, false);
  } catch (err) { setStatus('Error: ' + err.message); }
}

async function handleFolder(files) {
  setStatus('Packing folder…');
  try {
    const zip = new JSZip();
    const folderName = files[0].webkitRelativePath.split('/')[0];
    for (const f of files) zip.file(f.webkitRelativePath, await f.arrayBuffer());
    const zipData = await zip.generateAsync({ type: 'uint8array', compression: 'STORE' });
    lastRawData = zipData; lastFilename = folderName + '.zip'; lastIsDirectory = true;
    await prepare(zipData, folderName + '.zip', true);
  } catch (err) { setStatus('Error: ' + err.message); }
}

async function reprepare() {
  if (!lastRawData) return;
  if (timerId !== null) stopTransfer(false);
  await prepare(lastRawData, lastFilename, lastIsDirectory);
}

async function prepare(raw, filename, isDirectory) {
  setStatus('Compressing…');
  const origSize = raw.length;
  let data = raw;
  let compressed = false;

  if (raw.length >= 256) {
    const comp = pako.gzip(raw, { level: 6 });
    if (comp.length < raw.length * 0.95) { data = comp; compressed = true; }
  }

  const chunkSize = Math.max(50, parseInt(document.getElementById('chunkSize').value) || 600);
  const ec = document.getElementById('ecLevel').value;
  const rawChunks = [];
  for (let i = 0; i < data.length; i += chunkSize) rawChunks.push(data.slice(i, i + chunkSize));
  const total = rawChunks.length;

  framedChunks = rawChunks.map((c, i) => concat2(packHeader(0, i, total), c));
  paddedChunks = rawChunks.map(c => {
    if (c.length === chunkSize) return c;
    const p = new Uint8Array(chunkSize); p.set(c); return p;
  });
  isFountain = document.getElementById('fountainToggle').checked;

  const manifest = {
    v: 1, filename, size: data.length, original_size: origSize,
    compressed, is_directory: isDirectory,
    num_streams: 1, total_chunks: total, chunk_size: chunkSize,
    error_correction: ec, fountain: isFountain,
  };
  manifestBytes = buildManifestChunk(manifest);

  const ratio = compressed ? ` → ${fmtBytes(data.length)} gzip` : '';
  document.getElementById('fileInfo').innerHTML =
    `<div class="fname">${filename}</div>` +
    `<div>${fmtBytes(origSize)}${ratio} &nbsp;·&nbsp; ${total} chunks × ${chunkSize} B</div>` +
    `<div style="color:#555">EC: ${ec} &nbsp;·&nbsp; Mode: ${isFountain ? 'fountain' : 'sequential'} &nbsp;·&nbsp; ETA: <span id="etaVal">${calcEta(total)}</span></div>`;
  document.getElementById('fileInfo').classList.remove('hidden');
  document.getElementById('sTotal').textContent = total;
  document.getElementById('actionRow').classList.remove('hidden');
  setStatus('Ready — press Start Transfer.');
}

// ── Transfer ──────────────────────────────────────────────────────────────────
async function startTransfer() {
  if (!framedChunks.length) return;
  stopTransfer(false);
  buildGrid();

  isRunning = true;
  isPaused = false;
  isManifestPhase = true;
  seqPos = 0;
  cycleCount = 0;
  fountainSeed = 0;
  frameCount = 0;
  fpsAvg = 0;
  repeatCount = 0;
  rendering = false;
  lastFrameTs = performance.now();

  document.getElementById('startBtn').classList.add('hidden');
  document.getElementById('pauseBtn').classList.remove('hidden');
  document.getElementById('stopBtn').classList.remove('hidden');
  document.getElementById('qrSection').classList.remove('hidden');
  document.getElementById('qrPlaceholder')?.classList.add('hidden');
  document.getElementById('sCycles').textContent = 0;
  document.getElementById('sCodesFrame').textContent = numQR();
  setStatus('Transmitting…');

  await renderFrame();
  isPaused = true;
  document.getElementById('pauseBtn').textContent = 'Resume';
  setStatus('Paused on manifest — press Resume when receiver is ready.');

  const fps = Math.max(1, Math.min(30, parseInt(document.getElementById('fps').value) || 3));
  timerId = setInterval(tick, Math.round(1000 / fps));
}

async function tick() {
  if (isPaused || !isRunning || rendering) return;
  if (repeatCount > 0) { repeatCount--; return; }
  rendering = true;
  try { await renderFrame(); } finally { rendering = false; }
  const n = Math.max(1, parseInt(document.getElementById('chunkRepeat').value) || 1);
  repeatCount = n - 1;
}

async function renderFrame() {
  const count = numQR();
  const total = framedChunks.length;
  const size = canvasSize();
  const ec = document.getElementById('ecLevel').value;
  const opts = { errorCorrectionLevel: ec, margin: 3, width: size, color: { dark: '#000000', light: '#ffffff' } };

  if (canvases.length !== count) buildGrid();
  resizeCanvases(size);

  let renders;
  let firstSeq = 0;

  if (isManifestPhase) {
    // All slots show the manifest so the receiver is guaranteed to get it.
    const byteStr = toByteString(manifestBytes);
    renders = canvases.map(c => QRCode.toCanvas(c, [{ data: byteStr, mode: 'byte' }], opts));
  } else if (isFountain) {
    // Each slot gets a unique, independently-decodable packet.
    firstSeq = fountainSeed;
    renders = canvases.map((c, k) => {
      const pkt = buildFountainPacket(fountainSeed + k, paddedChunks);
      return QRCode.toCanvas(c, [{ data: toByteString(pkt), mode: 'byte' }], opts);
    });
    fountainSeed += count;
  } else {
    // Sequential: N consecutive chunks, wrapping at end of stream.
    const effectiveN = Math.min(count, total);
    firstSeq = seqPos;
    renders = canvases.map((c, k) => {
      if (k >= effectiveN) {
        // More grid slots than chunks — blank the surplus canvas.
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, size, size);
        return Promise.resolve();
      }
      return QRCode.toCanvas(c, [{ data: toByteString(framedChunks[(seqPos + k) % total]), mode: 'byte' }], opts);
    });
    seqPos += effectiveN;
    if (seqPos >= total) { seqPos %= total; cycleCount++; }
  }

  try {
    await Promise.all(renders);
  } catch (err) {
    setStatus('QR error: ' + err.message + ' — try smaller chunk size or reduce QR size per code.');
    stopTransfer(false);
    return;
  }

  // Pulse all canvases together on each data frame.
  if (!isManifestPhase) {
    for (const c of canvases) c.classList.remove('qr-new');
    void canvases[0]?.offsetWidth;
    for (const c of canvases) c.classList.add('qr-new');
  }

  const now = performance.now();
  fpsAvg = frameCount < 5 ? fpsAvg : Math.round(10000 / (now - lastFrameTs)) / 10;
  lastFrameTs = now;
  frameCount++;

  const chunkSize = Math.max(50, parseInt(document.getElementById('chunkSize').value) || 600);

  if (isManifestPhase) {
    document.getElementById('chunkLabel').innerHTML = '<span>MANIFEST</span>';
    document.getElementById('sFrame').textContent = 'M';
    document.getElementById('sCycles').textContent = 0;
    document.getElementById('sFps').textContent = '…';
    document.getElementById('sThroughput').textContent = '—';
    document.getElementById('progFill').style.width = '0%';
    isManifestPhase = false;
  } else {
    if (isFountain) {
      document.getElementById('chunkLabel').innerHTML =
        `fountain pkts <span>${firstSeq + 1}–${firstSeq + count}</span>`;
      document.getElementById('sFrame').textContent = firstSeq + 1;
      document.getElementById('sCycles').textContent = Math.floor(fountainSeed / total);
      document.getElementById('progFill').style.width =
        Math.round(((fountainSeed % total) / total) * 100) + '%';
    } else {
      const last = Math.min(firstSeq + count, total);
      document.getElementById('chunkLabel').innerHTML =
        `chunks <span>${firstSeq + 1}–${last}</span> / ${total}`;
      document.getElementById('sFrame').textContent = firstSeq + 1;
      document.getElementById('sCycles').textContent = cycleCount;
      document.getElementById('progFill').style.width =
        Math.round((seqPos / total) * 100) + '%';
    }
    document.getElementById('sFps').textContent = frameCount < 3 ? '…' : fpsAvg;
    document.getElementById('sThroughput').textContent =
      frameCount < 5 ? '…' : fmtRate((count * fpsAvg * chunkSize) / 1024);
  }
}

function togglePause() {
  isPaused = !isPaused;
  document.getElementById('pauseBtn').textContent = isPaused ? 'Resume' : 'Pause';
  setStatus(isPaused ? 'Paused.' : 'Transmitting…');
}

function stopTransfer(resetUI = true) {
  if (timerId) { clearInterval(timerId); timerId = null; }
  isRunning = false;
  isPaused = false;
  rendering = false;
  repeatCount = 0;
  if (resetUI) {
    document.getElementById('startBtn').textContent = 'Restart Transfer';
    document.getElementById('startBtn').classList.remove('hidden');
    document.getElementById('pauseBtn').classList.add('hidden');
    document.getElementById('stopBtn').classList.add('hidden');
    document.getElementById('qrSection').classList.add('hidden');
    document.getElementById('qrPlaceholder')?.classList.remove('hidden');
    setStatus('Stopped.');
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function setStatus(msg) { document.getElementById('statusMsg').textContent = msg; }

function fmtBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(2) + ' MB';
}

function fmtRate(kbs) {
  if (kbs < 1) return (kbs * 1024).toFixed(0) + ' B/s';
  if (kbs < 1024) return kbs.toFixed(1) + ' KB/s';
  return (kbs / 1024).toFixed(2) + ' MB/s';
}

function calcEta(total) {
  if (!total) return '—';
  const fps = Math.max(1, Math.min(30, parseInt(document.getElementById('fps').value) || 3));
  const repeat = Math.max(1, parseInt(document.getElementById('chunkRepeat').value) || 1);
  const frames = Math.ceil(total / numQR()) + 1; // +1 for manifest frame
  const secs = Math.round(frames * repeat / fps);
  if (secs < 60) return secs + 's';
  return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
}

function refreshEta() {
  const el = document.getElementById('etaVal');
  if (el) el.textContent = calcEta(framedChunks.length);
}

// ── Event listeners ───────────────────────────────────────────────────────────
document.getElementById('gridSelect').addEventListener('change', e => {
  const [c, r] = e.target.value.split('x').map(Number);
  gridCols = c; gridRows = r;
  if (isRunning) buildGrid();
  document.getElementById('sCodesFrame').textContent = numQR();
  refreshEta();
});

let reprepareTimer = null;
document.getElementById('chunkSize').addEventListener('input', () => {
  clearTimeout(reprepareTimer);
  reprepareTimer = setTimeout(reprepare, 600);
});
document.getElementById('ecLevel').addEventListener('change', reprepare);
document.getElementById('fountainToggle').addEventListener('change', reprepare);

['input', 'change'].forEach(ev => {
  document.getElementById('fps').addEventListener(ev, refreshEta);
  document.getElementById('chunkRepeat').addEventListener(ev, refreshEta);
  document.getElementById('qrSize').addEventListener(ev, refreshEta);
});
