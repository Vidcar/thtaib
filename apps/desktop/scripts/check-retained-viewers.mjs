import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repo = path.resolve(desktop, '../..');
const scratch = path.join(repo, '.scratch/retained-viewer-check');
fs.mkdirSync(scratch, { recursive: true });
const fixtureMain = path.join(scratch, 'viewer-main.cjs');
fs.copyFileSync(path.join(desktop, 'scripts/fixtures/check-retained-viewers.cjs'), fixtureMain);
const require = createRequire(path.join(desktop, 'package.json'));
const { createServer } = require('vite');
const server = await createServer({ configFile: false, root: path.join(desktop, 'scripts/fixtures'), server: { host: '127.0.0.1', port: 0, watch: null, fs: { allow: [repo] } }, resolve: { dedupe: ['react','react-dom'], alias: { react: path.join(desktop, 'node_modules/react'), 'react-dom': path.join(desktop, 'node_modules/react-dom') } }, esbuild: { jsx: 'automatic' }, logLevel: 'error' });
try {
  await server.listen();
  const url = server.resolvedUrls.local[0] + 'retained-viewers.html';
  const child = spawn(require('electron'), [fixtureMain, url], { cwd: scratch, env: { ...process.env, WORKBENCH_VIEWER_SCRATCH: scratch }, stdio: 'inherit', windowsHide: true });
  const timeout = setTimeout(() => child.kill(), 30_000);
  try { process.exitCode = await new Promise((resolve, reject) => { child.on('error', reject); child.on('exit', code => resolve(code ?? 1)); }); }
  finally { clearTimeout(timeout); }
} finally { await server.close(); }
