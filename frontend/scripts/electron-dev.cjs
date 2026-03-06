#!/usr/bin/env node
/**
 * Start Vite dev server and Electron, using env-configured ports.
 * - Uses VITE_PORT (defaults 5173)
 * - Uses VITE_DEV_SERVER_URL (defaults http://localhost:<VITE_PORT>)
 * - Exits if Vite can't start (e.g. port in use)
 */
const { spawn } = require('child_process')
const http = require('http')
const path = require('path')
const net = require('net')

const isWindows = process.platform === 'win32'
const cwd = path.resolve(__dirname, '..')

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.unref()
    server.on('error', () => resolve(false))
    // Match Vite default: localhost/127.0.0.1
    server.listen({ port, host: '127.0.0.1' }, () => server.close(() => resolve(true)))
  })
}

async function findFreePort(startPort, maxTries = 50) {
  for (let p = startPort; p < startPort + maxTries; p++) {
    // eslint-disable-next-line no-await-in-loop
    if (await isPortFree(p)) return p
  }
  return null
}

async function main() {
  const desired = parseInt(process.env.VITE_PORT || '5173', 10)
  const vitePort = await findFreePort(desired)
  if (!vitePort) {
    console.error(`No free Vite port found starting at ${desired}`)
    process.exit(1)
  }
  // Force Vite to bind to IPv4 localhost so our port checks match.
  const devUrl = process.env.VITE_DEV_SERVER_URL || `http://127.0.0.1:${vitePort}`

function waitForHttp(url, timeoutMs = 30_000) {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(url, (res) => {
        res.resume()
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 500) return resolve()
        if (Date.now() - start > timeoutMs) return reject(new Error(`Timed out waiting for ${url}`))
        setTimeout(tick, 300)
      })
      req.on('error', () => {
        if (Date.now() - start > timeoutMs) return reject(new Error(`Timed out waiting for ${url}`))
        setTimeout(tick, 300)
      })
    }
    tick()
  })
}

  const vite = spawn(
    isWindows ? 'npx.cmd' : 'npx',
    ['vite', '--host', '127.0.0.1', '--port', String(vitePort), '--strictPort'],
    {
    cwd,
    stdio: 'inherit',
    shell: false,
    env: { ...process.env, VITE_PORT: String(vitePort), VITE_DEV_SERVER_URL: devUrl },
    }
  )

  let electron = null

  async function startElectron() {
    await waitForHttp(devUrl)
    electron = spawn(isWindows ? 'npx.cmd' : 'npx', ['electron', '.', '--dev'], {
      cwd,
      stdio: 'inherit',
      shell: false,
      env: { ...process.env, VITE_DEV_SERVER_URL: devUrl },
    })
    electron.on('exit', (code) => {
      // When the Electron window closes, shut down Vite too.
      try { vite.kill() } catch {}
      if (code !== 0 && code !== null) process.exit(code)
      process.exit(0)
    })
  }

  startElectron().catch((e) => {
    console.error(e.message || String(e))
    process.exit(1)
  })

  function killAll() {
    try { vite.kill() } catch {}
    try { electron && electron.kill() } catch {}
    process.exit(0)
  }

  process.on('SIGINT', killAll)
  process.on('SIGTERM', killAll)

  vite.on('exit', (code) => {
    if (code !== 0 && code !== null) process.exit(code)
  })
}

main().catch((e) => {
  console.error(e.message || String(e))
  process.exit(1)
})

