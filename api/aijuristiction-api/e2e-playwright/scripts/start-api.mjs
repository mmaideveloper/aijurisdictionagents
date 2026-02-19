import { spawn, spawnSync } from 'node:child_process';
import { accessSync, constants } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const e2eRoot = path.resolve(scriptDir, '..');
const apiRoot = path.resolve(e2eRoot, '..');
const repoRoot = path.resolve(apiRoot, '..', '..');

const host = process.env.API_HOST ?? '127.0.0.1';
const port = process.env.API_PORT ?? '8080';

function isExecutable(filePath) {
  try {
    accessSync(filePath, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function commandExists(command) {
  const result = spawnSync(command, ['--version'], {
    stdio: 'ignore',
  });
  return result.status === 0 && !result.error;
}

function resolvePythonCommand() {
  if (process.env.API_PYTHON) {
    return process.env.API_PYTHON;
  }

  const localCondaPython =
    process.platform === 'win32'
      ? path.join(repoRoot, '.conda', 'python.exe')
      : path.join(repoRoot, '.conda', 'bin', 'python');

  const localCondaAltPython =
    process.platform === 'win32'
      ? path.join(repoRoot, 'conda', 'python.exe')
      : path.join(repoRoot, 'conda', 'bin', 'python');

  const localCandidates = [localCondaPython, localCondaAltPython];
  for (const candidate of localCandidates) {
    if (isExecutable(candidate)) {
      return candidate;
    }
  }

  const candidates =
    process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'];
  for (const candidate of candidates) {
    if (commandExists(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    `No Python interpreter found. Set API_PYTHON or create local env at ${localCondaPython} or ${localCondaAltPython}.`
  );
}

const python = resolvePythonCommand();
const args = ['-m', 'uvicorn', 'app.main:app', '--host', host, '--port', port];

console.log(
  `[playwright-api] starting: ${python} ${args.join(' ')} (cwd=${apiRoot})`
);

const child = spawn(python, args, {
  cwd: apiRoot,
  stdio: 'inherit',
  env: process.env,
});

child.on('error', (error) => {
  console.error(`[playwright-api] failed to launch API: ${error.message}`);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

function shutdown(signal) {
  if (!child.killed) {
    child.kill(signal);
  }
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
