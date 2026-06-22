/**
 * Live behavioral test for server-side frame dropping (issue #30).
 *
 * Unlike test_backpressure_gap.js (which proves the codec stays bit-exact across
 * a gap), this one runs the REAL server loop end-to-end and proves the drop
 * mechanism actually fires: a client that reports a high decode backlog receives
 * a stream with SKIPPED frame indices, while a client reporting zero backlog
 * receives every frame in order.
 *
 * It generates a short clip with ffmpeg, launches stream_server.py, then opens
 * two WebSocket clients over the same wall-clock window and compares what each
 * received. Frame indices are read straight from the 4-byte big-endian header,
 * so no decode is needed.
 *
 * Requires: ffmpeg, and a Python with the server deps (fastapi/uvicorn/opencv).
 *   Override the interpreter with ASCIL_PY (e.g. ASCIL_PY=/data/ascil-venv/bin/python).
 *
 * Usage: node test/test_backpressure_live.js
 */
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const net = require('net');
const path = require('path');

const PY = process.env.ASCIL_PY || 'python3';
const REPO = path.dirname(__dirname);
const WINDOW_MS = 2500;       // collection window per client
const HIGH_BACKLOG = 50;      // well above the server's BACKLOG_HIGH (8)

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function waitForPort(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tryOnce = () => {
      const sock = net.connect(port, '127.0.0.1');
      sock.on('connect', () => { sock.destroy(); resolve(); });
      sock.on('error', () => {
        sock.destroy();
        if (Date.now() > deadline) reject(new Error('server did not start'));
        else setTimeout(tryOnce, 150);
      });
    };
    tryOnce();
  });
}

// Collect frame indices for WINDOW_MS. If reportDepth is set, spam buffer reports.
function collect(port, reportDepth) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws?codec=adaptive`);
    ws.binaryType = 'arraybuffer';
    const indices = [];
    let reporter = null, timer = null;

    const stop = () => {
      if (reporter) clearInterval(reporter);
      if (timer) clearTimeout(timer);
      try { ws.close(); } catch (_) {}
      resolve(indices);
    };

    ws.onopen = () => {
      timer = setTimeout(stop, WINDOW_MS);
      if (reportDepth != null) {
        const send = () => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'buffer', depth: reportDepth }));
          }
        };
        send();
        reporter = setInterval(send, 100);
      }
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') return; // INIT / status
      indices.push(new DataView(ev.data).getUint32(0, false));
    };
    ws.onerror = (e) => { if (timer) clearTimeout(timer); reject(e.error || new Error('ws error')); };
  });
}

function maxGap(indices) {
  let m = 0;
  for (let i = 1; i < indices.length; i++) m = Math.max(m, indices[i] - indices[i - 1]);
  return m;
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ascil-bp-'));
  const clip = path.join(tmp, 'clip.mp4');
  let server = null;
  try {
    // 6s of moving content at 24fps so consecutive frames differ (real deltas).
    execFileSync('ffmpeg', [
      '-y', '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=24:duration=6',
      '-pix_fmt', 'yuv420p', clip,
    ], { stdio: 'ignore' });

    const port = await freePort();
    // stdin must stay OPEN: the server runs an interactive command loop on the
    // main thread (uvicorn is a daemon thread), and EOF on stdin kills it.
    server = spawn(PY, ['stream_server.py', clip, '--mode', '2', '--vol', '0',
      '--cols', '80', '--no-thumbnails', '--host', '127.0.0.1', '--port', String(port)],
      { cwd: REPO, stdio: ['pipe', 'ignore', 'ignore'] });
    server.on('error', (e) => { throw e; });

    await waitForPort(port, 15000);

    // Control first (every frame), then backpressure (high backlog). Each ws
    // connection replays the clip from index 0.
    const control = await collect(port, 0);
    const slow = await collect(port, HIGH_BACKLOG);

    const checks = [
      ['control client received frames', control.length > 5, `got ${control.length}`],
      ['control stream is contiguous (no server drops)', maxGap(control) <= 1,
        `maxGap=${maxGap(control)}`],
      ['backpressure client received some frames (not starved)', slow.length > 0,
        `got ${slow.length}`],
      ['backpressure stream has skipped indices (drops fired)', maxGap(slow) > 1,
        `maxGap=${maxGap(slow)}`],
      ['backpressure received fewer frames than control', slow.length < control.length,
        `slow=${slow.length} control=${control.length}`],
    ];

    let failed = 0;
    for (const [name, ok, why] of checks) {
      console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + why}`);
      if (!ok) failed++;
    }
    console.log(`\ncontrol: ${control.length} frames (maxGap ${maxGap(control)})  |  ` +
      `backpressure: ${slow.length} frames (maxGap ${maxGap(slow)})`);
    console.log(`${checks.length - failed}/${checks.length} passed`);
    process.exitCode = failed === 0 ? 0 : 1;
  } finally {
    if (server) server.kill('SIGKILL');
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error('ERROR', e); process.exit(2); });
