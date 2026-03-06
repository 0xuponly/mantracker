#!/usr/bin/env node
/**
 * Single command to start backend (FastAPI) and frontend (Electron).
 * Run from repo root: npm start
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');
const root = path.resolve(__dirname, '..');

const isWindows = process.platform === 'win32';
const venvPython = path.join(
  root,
  'backend',
  isWindows ? path.join('.venv', 'Scripts', 'python.exe') : path.join('.venv', 'bin', 'python')
);
if (!fs.existsSync(venvPython)) {
  console.error('Backend venv not found. Run first:');
  console.error('  cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt');
  process.exit(1);
}

const uvicornArgs = [
  '-m', 'uvicorn',
  'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000',
];

function canListen(port, host) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.on('error', () => resolve(false));
    server.listen({ port, host }, () => {
      server.close(() => resolve(true));
    });
  });
}

async function findFreePort(startPort, isFree, maxTries = 50) {
  for (let p = startPort; p < startPort + maxTries; p++) {
    // eslint-disable-next-line no-await-in-loop
    if (await isFree(p)) return p;
  }
  return null;
}

let backend = null;
let frontend = null;

(async () => {
  // Backend binds to 0.0.0.0, so check port availability on that host.
  const backendPort = await findFreePort(8000, (p) => canListen(p, '0.0.0.0'));
  if (!backendPort) {
    console.error('No free backend port found starting at 8000.');
    process.exit(1);
  }
  // Vite binds on localhost by default; check 127.0.0.1 to match typical dev usage.
  const vitePort = await findFreePort(5173, (p) => canListen(p, '127.0.0.1'));
  if (!vitePort) {
    console.error('No free frontend port found starting at 5173.');
    process.exit(1);
  }

  const backendUrl = `http://127.0.0.1:${backendPort}`;
  // Use IPv4 loopback consistently (Vite dev script binds to 127.0.0.1)
  const viteUrl = `http://127.0.0.1:${vitePort}`;

  const uvicornArgs2 = [
    '-m', 'uvicorn',
    'app.main:app', '--reload', '--host', '0.0.0.0', '--port', String(backendPort),
  ];

  backend = spawn(venvPython, uvicornArgs2, {
    cwd: path.join(root, 'backend'),
    stdio: 'inherit',
    shell: isWindows,
    env: { ...process.env },
  });

  frontend = spawn(isWindows ? 'npm.cmd' : 'npm', ['run', 'electron:dev'], {
    cwd: path.join(root, 'frontend'),
    stdio: 'inherit',
    shell: true,
    env: {
      ...process.env,
      BACKEND_URL: backendUrl,
      VITE_PORT: String(vitePort),
      VITE_DEV_SERVER_URL: viteUrl,
    },
  });

function killAll() {
  try { backend && backend.kill(); } catch {}
  try { frontend && frontend.kill(); } catch {}
  process.exit(0);
}

process.on('SIGINT', killAll);
process.on('SIGTERM', killAll);

backend.on('error', (err) => {
  console.error('Backend failed to start. Ensure backend/.venv exists and run: cd backend && pip install -r requirements.txt');
  console.error(err.message);
  killAll();
});

frontend.on('error', (err) => {
  console.error('Frontend failed to start:', err.message);
  killAll();
});

backend.on('exit', (code) => {
  // If backend stops for any reason, stop frontend too.
  try { frontend && frontend.kill(); } catch {}
  if (code !== 0 && code !== null) process.exit(code);
  process.exit(0);
});
frontend.on('exit', (code) => {
  // If frontend is closed, stop backend as well.
  try { backend && backend.kill(); } catch {}
  if (code !== 0 && code !== null) process.exit(code);
  process.exit(0);
});
})();
