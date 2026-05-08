'use strict';

// ── Protocol ────────────────────────────────────────────────────────────────
const HEADER_SIZE = 9;
const MANIFEST_STREAM_ID = 255;

function packHeader(streamId, sequence, totalChunks) {
  const buf = new ArrayBuffer(9);
  const v = new DataView(buf);
  v.setUint8(0, streamId);
  v.setUint32(1, sequence, false);   // big-endian
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

// qrcode library needs byte data as a Latin-1 string
function toByteString(u8) {
  let s = '';
  for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
  return s;
}

// ── State ────────────────────────────────────────────────────────────────────
let framedChunks = [];   // Uint8Array[] – each has 9-byte header prepended
let manifestBytes = null;
let currentIdx = 0;      // 0 = manifest, 1…N = data chunks
let cycleCount = 0;
let isPaused = false;
let timerId = null;
let lastFrameTs = 0;
let frameCount = 0;
let fpsAvg = 0;
let replayChunks = null; // null = normal mode; array of 0-based indices = replay mode
let replayPos = 0;
let replayCycles = 0;
let repeatCount = 0;    // ticks remaining on current frame before advancing
let lastRawData = null;
let lastFilename = null;
let lastIsDirectory = false;

// ── File reading ─────────────────────────────────────────────────────────────
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
  } catch (err) {
    setStatus('Error reading file: ' + err.message);
  }
}

async function handleFolder(files) {
  setStatus('Packing folder into zip…');
  try {
    const zip = new JSZip();
    const folderName = files[0].webkitRelativePath.split('/')[0];
    for (const f of files) {
      zip.file(f.webkitRelativePath, await f.arrayBuffer());
    }
    const zipData = await zip.generateAsync({ type: 'uint8array', compression: 'STORE' });
    lastRawData = zipData; lastFilename = folderName + '.zip'; lastIsDirectory = true;
    await prepare(zipData, folderName + '.zip', true);
  } catch (err) {
    setStatus('Error packing folder: ' + err.message);
  }
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
    if (comp.length < raw.length * 0.95) {
      data = comp;
      compressed = true;
    }
  }

  const chunkSize = Math.max(50, parseInt(document.getElementById('chunkSize').value) || 600);
  const ec = document.getElementById('ecLevel').value;

  // Split into raw chunks
  const rawChunks = [];
  for (let i = 0; i < data.length; i += chunkSize) {
    rawChunks.push(data.slice(i, i + chunkSize));
  }
  const total = rawChunks.length;

  // Frame each chunk with 9-byte header
  framedChunks = rawChunks.map((c, i) => concat2(packHeader(0, i, total), c));

  // Build manifest
  const manifest = {
    v: 1, filename, size: data.length, original_size: origSize,
    compressed, is_directory: isDirectory,
    num_streams: 1, total_chunks: total, chunk_size: chunkSize, error_correction: ec,
  };
  manifestBytes = buildManifestChunk(manifest);

  // Show info
  const ratio = compressed ? ` → ${fmtBytes(data.length)} gzip` : '';
  document.getElementById('fileInfo').innerHTML =
    `<div class="fname">${filename}</div>` +
    `<div>${fmtBytes(origSize)}${ratio} &nbsp;·&nbsp; ${total} chunks × ${chunkSize} B</div>` +
    `<div style="color:#555">Manifest: ${manifestBytes.length} B &nbsp;·&nbsp; EC: ${ec} &nbsp;·&nbsp; ETA: <span id="etaVal">${calcEta(total)}</span></div>`;
  document.getElementById('fileInfo').classList.remove('hidden');

  document.getElementById('sTotal').textContent = total;
  document.getElementById('actionRow').classList.remove('hidden');
  document.getElementById('replaySection').classList.remove('hidden');
  document.getElementById('startBtn').textContent = 'Start Transfer';
  setStatus('Ready — press Start Transfer.');
}

// ── Transfer display ─────────────────────────────────────────────────────────
async function startTransfer() {
  if (!framedChunks.length) return;
  stopTransfer(false);

  currentIdx = 0;
  cycleCount = 0;
  isPaused = false;
  frameCount = 0;
  fpsAvg = 0;
  repeatCount = 0;
  lastFrameTs = performance.now();

  document.getElementById('startBtn').classList.add('hidden');
  document.getElementById('pauseBtn').classList.remove('hidden');
  document.getElementById('stopBtn').classList.remove('hidden');
  document.getElementById('qrSection').classList.remove('hidden');
  document.getElementById('sCycles').textContent = 0;
  setStatus('Transmitting…');

  const fps = Math.max(1, Math.min(15, parseInt(document.getElementById('fps').value) || 3));
  const delay = Math.round(1000 / fps);

  await renderFrame();
  isPaused = true;
  document.getElementById('pauseBtn').textContent = 'Resume';
  setStatus('Paused on manifest — press Resume when receiver is ready.');
  timerId = setInterval(tick, delay);
}

async function tick() {
  if (isPaused) return;
  if (repeatCount > 0) { repeatCount--; return; }
  await renderFrame();
  const n = Math.max(1, parseInt(document.getElementById('chunkRepeat').value) || 1);
  repeatCount = n - 1;
}

async function renderFrame() {
  const canvas = document.getElementById('qrCanvas');
  const size = Math.max(100, parseInt(document.getElementById('qrSize').value) || 420);
  const ec = document.getElementById('ecLevel').value;

  let isManifest = false, data, frameSeq, frameLabel;
  if (replayChunks !== null) {
    frameSeq = replayChunks[replayPos];
    data = framedChunks[frameSeq];
    frameLabel = `${frameSeq + 1} / ${framedChunks.length}`;
    replayPos++;
    if (replayPos >= replayChunks.length) { replayPos = 0; replayCycles++; }
  } else {
    isManifest = (currentIdx === 0);
    data = isManifest ? manifestBytes : framedChunks[currentIdx - 1];
    frameSeq = isManifest ? null : currentIdx - 1;
    frameLabel = isManifest ? 'MANIFEST' : `${currentIdx} / ${framedChunks.length}`;
  }

  try {
    await QRCode.toCanvas(canvas, [{ data: toByteString(data), mode: 'byte' }], {
      errorCorrectionLevel: ec,
      margin: 3,
      width: size,
      color: { dark: '#000000', light: '#ffffff' }
    });
  } catch (err) {
    setStatus('QR error: ' + err.message + ' — try reducing chunk size.');
    stopTransfer(false);
    return;
  }

  const now = performance.now();
  const elapsed = now - lastFrameTs;
  lastFrameTs = now;
  frameCount++;
  fpsAvg = frameCount < 5 ? fpsAvg : Math.round(10000 / elapsed) / 10;

  document.getElementById('chunkLabel').innerHTML =
    isManifest ? '<span>MANIFEST</span>' : `chunk <span>${frameLabel}</span>`;
  document.getElementById('sFrame').textContent = isManifest ? 'M' : (replayChunks !== null ? frameSeq + 1 : currentIdx);
  document.getElementById('sCycles').textContent = replayChunks !== null ? replayCycles : cycleCount;
  document.getElementById('sFps').textContent = frameCount < 3 ? '…' : fpsAvg;
  const pct = isManifest ? 0 : replayChunks !== null
    ? Math.round((replayPos / replayChunks.length) * 100)
    : Math.round((currentIdx / framedChunks.length) * 100);
  document.getElementById('progFill').style.width = pct + '%';

  if (replayChunks === null) {
    currentIdx++;
    if (currentIdx > framedChunks.length) {
      currentIdx = 0;
      cycleCount++;
      document.getElementById('sCycles').textContent = cycleCount;
    }
  }
}

function togglePause() {
  isPaused = !isPaused;
  document.getElementById('pauseBtn').textContent = isPaused ? 'Resume' : 'Pause';
  setStatus(isPaused ? 'Paused.' : 'Transmitting…');
}

function startReplay() {
  if (!framedChunks.length) return;
  const input = document.getElementById('missingInput').value.trim();
  if (!input) { setStatus('Enter chunk numbers to replay.'); return; }
  const parsed = parseChunkExpression(input, framedChunks.length);
  const indices = parsed.map(n => n - 1);
  if (!indices.length) { setStatus('No valid chunks — use numbers (3,7), ranges (5-10), or comparisons (>=50, <60).'); return; }

  stopTransfer(false);
  replayChunks = indices;
  replayPos = 0;
  replayCycles = 0;
  isPaused = false;
  frameCount = 0;
  fpsAvg = 0;
  repeatCount = 0;
  lastFrameTs = performance.now();

  document.getElementById('startBtn').classList.add('hidden');
  document.getElementById('pauseBtn').classList.remove('hidden');
  document.getElementById('stopBtn').classList.remove('hidden');
  document.getElementById('qrSection').classList.remove('hidden');
  document.getElementById('sCycles').textContent = 0;
  setStatus(`Replaying ${indices.length} missing chunk(s)…`);

  const fps = Math.max(1, Math.min(15, parseInt(document.getElementById('fps').value) || 3));
  renderFrame();
  timerId = setInterval(tick, Math.round(1000 / fps));
}

function stopTransfer(resetUI = true) {
  if (timerId) { clearInterval(timerId); timerId = null; }
  isPaused = false;
  replayChunks = null;
  replayPos = 0;
  repeatCount = 0;
  if (resetUI) {
    document.getElementById('startBtn').textContent = 'Restart Transfer';
    document.getElementById('startBtn').classList.remove('hidden');
    document.getElementById('pauseBtn').classList.add('hidden');
    document.getElementById('stopBtn').classList.add('hidden');
    setStatus('Stopped.');
  }
}

// ── Utilities ────────────────────────────────────────────────────────────────
function setStatus(msg) { document.getElementById('statusMsg').textContent = msg; }

function fmtBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(2) + ' MB';
}

function calcEta(totalChunks) {
  const fps    = Math.max(1, Math.min(15, parseInt(document.getElementById('fps').value) || 3));
  const repeat = Math.max(1, parseInt(document.getElementById('chunkRepeat').value) || 1);
  const secs = Math.round((totalChunks + 1) * repeat / fps);
  if (secs < 60) return secs + 's';
  return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
}

function parseChunkExpression(input, total) {
  const tokens = input.split(/\s*,\s*/).map(s => s.trim()).filter(Boolean);
  const result = new Set();
  let lo = null, hi = null;
  for (const tok of tokens) {
    let m;
    if      ((m = tok.match(/^>=(\d+)$/)))      { const v = +m[1];     lo = lo === null ? v : Math.max(lo, v); }
    else if ((m = tok.match(/^>(\d+)$/) ))      { const v = +m[1] + 1; lo = lo === null ? v : Math.max(lo, v); }
    else if ((m = tok.match(/^<=(\d+)$/)))      { const v = +m[1];     hi = hi === null ? v : Math.min(hi, v); }
    else if ((m = tok.match(/^<(\d+)$/) ))      { const v = +m[1] - 1; hi = hi === null ? v : Math.min(hi, v); }
    else if ((m = tok.match(/^(\d+)-(\d+)$/))) {
      const a = Math.min(+m[1], +m[2]), b = Math.max(+m[1], +m[2]);
      for (let i = a; i <= b && i <= total; i++) if (i >= 1) result.add(i);
    } else if ((m = tok.match(/^(\d+)$/))) {
      const n = +m[1];
      if (n >= 1 && n <= total) result.add(n);
    }
  }
  if (lo !== null || hi !== null) {
    const start = lo !== null ? lo : 1;
    const end   = hi !== null ? hi : total;
    for (let i = Math.max(1, start); i <= Math.min(total, end); i++) result.add(i);
  }
  return [...result].sort((a, b) => a - b);
}

let reprepareTimer = null;
document.getElementById('chunkSize').addEventListener('input', () => {
  clearTimeout(reprepareTimer);
  reprepareTimer = setTimeout(reprepare, 600);
});
document.getElementById('ecLevel').addEventListener('change', reprepare);
document.getElementById('fps').addEventListener('input', () => {
  const el = document.getElementById('etaVal');
  if (el) el.textContent = calcEta(framedChunks.length);
});
document.getElementById('chunkRepeat').addEventListener('input', () => {
  const el = document.getElementById('etaVal');
  if (el) el.textContent = calcEta(framedChunks.length);
});
