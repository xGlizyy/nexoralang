'use strict';

// Tests of the npm launcher. They run the real `bin/nex.js` with the Python of this machine.

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { findPython, describeFailure, candidates, windowsInstallations, isEnough, NO_PYTHON_EXIT_CODE } = require('../lib/python.js');

const ROOT = path.join(__dirname, '..');
const LAUNCHER = path.join(ROOT, 'bin', 'nex.js');
const EXAMPLES = path.join(ROOT, '..', 'nexora', 'examples');
const VERSION = require('../package.json').version;

// On Windows, Python writes text output with CRLF line endings.
const lines = (text) => text.replace(/\r\n/g, '\n');

function nex(args, options = {}) {
  return spawnSync(process.execPath, [LAUNCHER, ...args], {
    encoding: 'utf8',
    env: { ...process.env, ...options.env },
    cwd: options.cwd,
  });
}

test('the launcher runs the bundled interpreter', () => {
  const result = nex(['--version']);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), `NEXORA ${VERSION}`);
});

test('it runs a program and passes its output through', () => {
  const result = nex(['run', path.join(EXAMPLES, 'hello.nex')]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(lines(result.stdout), 'Hello from NEXORA\n');
  assert.equal(result.stderr, '');
});

test('exit codes are those of the interpreter', () => {
  assert.equal(nex(['check', path.join(EXAMPLES, 'invalid', 'type_errors.nex')]).status, 1);
  assert.equal(nex(['run', path.join(EXAMPLES, 'failing', 'runtime_error.nex')]).status, 3);
  assert.equal(nex(['run', path.join(EXAMPLES, 'failing', 'contract_violation.nex')]).status, 5);
  assert.equal(nex(['run', 'does-not-exist.nex']).status, 4);
  assert.equal(nex(['no-such-command']).status, 2);
});

test('JSON output stays clean JSON through the launcher', () => {
  const result = nex(['check', path.join(EXAMPLES, 'invalid', 'type_errors.nex'), '--format', 'json']);
  const document = JSON.parse(result.stdout);
  assert.equal(document.schema, 'nexora.diagnostics/1');
  assert.equal(document.ok, false);
  assert.equal(result.stderr, '');
});

test('relative paths are resolved from the directory of the caller', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'nexora-npm-'));
  try {
    fs.writeFileSync(path.join(directory, 'local.nex'), 'fn main() -> Void {\n    print(6 * 7)\n}\n');
    const result = nex(['run', 'local.nex'], { cwd: directory });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(lines(result.stdout), '42\n');
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('the bundled copy is used even if another nexora is importable', () => {
  // PYTHONPATH points to a fake package; the script directory still comes first.
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'nexora-npm-'));
  try {
    fs.mkdirSync(path.join(directory, 'nexora'));
    fs.writeFileSync(path.join(directory, 'nexora', '__init__.py'), 'raise SystemExit("wrong copy")\n');
    const result = nex(['--version'], { env: { PYTHONPATH: directory } });
    assert.equal(result.stdout.trim(), `NEXORA ${VERSION}`);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('without a usable Python it says so and exits with 127', () => {
  const result = nex(['--version'], { env: { NEXORA_PYTHON: path.join(os.tmpdir(), 'no-such-python') } });
  assert.equal(result.status, NO_PYTHON_EXIT_CODE);
  assert.equal(result.stdout, '');
  assert.match(result.stderr, /needs Python 3\.11 or newer/);
  assert.match(result.stderr, /NEXORA_PYTHON is set/);
});

test('NEXORA_PYTHON chooses the Python', () => {
  const found = findPython(process.env);
  assert.ok(found.python, 'the tests need a Python 3.11+ on this machine');
  // A command with arguments (py -3) cannot be given through the variable: skip that case.
  if (found.python.args.length === 0) {
    const result = nex(['--version'], { env: { NEXORA_PYTHON: found.python.command } });
    assert.equal(result.stdout.trim(), `NEXORA ${VERSION}`);
  }
});

test('the search order and the version rule', () => {
  assert.deepEqual(candidates({}, 'linux').map((c) => c.command), ['python3', 'python']);
  assert.deepEqual(candidates({}, 'win32').map((c) => c.command), ['py', 'python3', 'python']);
  // On Windows, the folders of the official installer come last, newest version first.
  const folders = { 'C:\\Users\\me\\AppData\\Local\\Programs\\Python': ['Python39', 'Python312', 'Launcher'],
    'C:\\Program Files': ['Python313', 'Git'] };
  const installed = windowsInstallations(
    { LOCALAPPDATA: 'C:\\Users\\me\\AppData\\Local', ProgramFiles: 'C:\\Program Files' },
    (directory) => folders[directory] || [],
  );
  assert.deepEqual(installed.map((c) => c.command), [
    'C:\\Program Files\\Python313\\python.exe',
    'C:\\Users\\me\\AppData\\Local\\Programs\\Python\\Python312\\python.exe',
    'C:\\Users\\me\\AppData\\Local\\Programs\\Python\\Python39\\python.exe',
  ]);
  assert.deepEqual(candidates({ NEXORA_PYTHON: '/opt/py' }, 'linux'), [{ command: '/opt/py', args: [] }]);
  assert.equal(isEnough([3, 11]), true);
  assert.equal(isEnough([3, 13]), true);
  assert.equal(isEnough([4, 0]), true);
  assert.equal(isEnough([3, 10]), false);
  assert.equal(isEnough([2, 7]), false);
});

test('an old Python is skipped and the next one is used', () => {
  const versions = { python3: [3, 9], python: [3, 12] };
  const found = findPython({}, (candidate) => versions[candidate.command] || null, 'linux');
  assert.equal(found.python.command, 'python');

  const none = findPython({}, (candidate) => (candidate.command === 'python3' ? [3, 9] : null), 'linux');
  assert.equal(none.python, null);
  const message = describeFailure(none);
  assert.match(message, /python3: is Python 3\.9, which is too old/);
  assert.match(message, /python: not found/);
  assert.match(message, /python\.org/);
});

test('the package carries every module of the interpreter and nothing else from the repository', () => {
  const source = fs.readdirSync(path.join(ROOT, '..', 'nexora', 'src', 'nexora')).filter((n) => n.endsWith('.py')).sort();
  const bundled = fs.readdirSync(path.join(ROOT, 'python', 'nexora')).filter((n) => n !== '__pycache__').sort();
  assert.deepEqual(bundled, source);
  for (const name of source) {
    assert.equal(
      fs.readFileSync(path.join(ROOT, 'python', 'nexora', name), 'utf8'),
      fs.readFileSync(path.join(ROOT, '..', 'nexora', 'src', 'nexora', name), 'utf8'),
      name,
    );
  }
});

test('npm test runs every test file of the package, and only files that exist', () => {
  // `node --test` accepts glob patterns only from Node 21, and engines allows Node 18, so the test
  // script names each file. A file added to test/ but not to the script would never run.
  const listed = require('../package.json').scripts.test.split(/\s+/).filter((word) => word.startsWith('test/'));
  const present = fs.readdirSync(__dirname).filter((name) => name.endsWith('.test.js')).map((name) => `test/${name}`);
  assert.deepEqual(present.filter((file) => !listed.includes(file)), [], 'test files that `npm test` does not run');
  assert.deepEqual(listed.filter((file) => !present.includes(file)), [], 'files in `npm test` that do not exist');
});
