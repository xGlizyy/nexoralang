'use strict';

// Finds a Python that can run NEXORA's interpreter.

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const MINIMUM = [3, 11];
// The script that starts the interpreter bundled in this package.
const ENTRY_POINT = path.join(__dirname, '..', 'python', 'nex_main.py');
// What `nex` exits with when no usable Python is found (the shell convention for
// "command not found"). The interpreter itself never uses this code.
const NO_PYTHON_EXIT_CODE = 127;

const PROBE = 'import sys; print("%d.%d" % sys.version_info[:2])';

// Commands to try, in order. On Windows `py -3` is the official launcher.
function candidates(env, platform = process.platform) {
  if (env.NEXORA_PYTHON) {
    return [{ command: env.NEXORA_PYTHON, args: [] }];
  }
  const list = [{ command: 'python3', args: [] }, { command: 'python', args: [] }];
  if (platform === 'win32') {
    list.unshift({ command: 'py', args: ['-3'] });
    list.push(...windowsInstallations(env));
  }
  return list;
}

// On Windows a Python can be installed without being on the PATH of the current terminal
// (and `python` may be the Microsoft Store placeholder, which is not a Python). These are
// the folders the official installer uses, newest version first.
function windowsInstallations(env, listDirectory = safeReaddir) {
  const found = [];
  for (const base of [env.LOCALAPPDATA && path.win32.join(env.LOCALAPPDATA, 'Programs', 'Python'),
    env.ProgramFiles, env['ProgramFiles(x86)']]) {
    if (!base) {
      continue;
    }
    for (const name of listDirectory(base)) {
      const match = /^Python3(\d+)(-32)?$/i.exec(name);
      if (match) {
        found.push({ minor: Number(match[1]), command: path.win32.join(base, name, 'python.exe') });
      }
    }
  }
  found.sort((a, b) => b.minor - a.minor);
  return found.map(({ command }) => ({ command, args: [] }));
}

function safeReaddir(directory) {
  try {
    return fs.readdirSync(directory);
  } catch {
    return [];
  }
}

// The version of a Python as [major, minor], or null if the command is not a working Python.
function versionOf(candidate) {
  const result = spawnSync(candidate.command, [...candidate.args, '-c', PROBE], {
    encoding: 'utf8',
    windowsHide: true,
    timeout: 15000,
  });
  if (result.error || result.status !== 0) {
    return null;
  }
  const match = /^(\d+)\.(\d+)\s*$/.exec(result.stdout);
  return match ? [Number(match[1]), Number(match[2])] : null;
}

function isEnough(version) {
  return version[0] > MINIMUM[0] || (version[0] === MINIMUM[0] && version[1] >= MINIMUM[1]);
}

// Returns { python } with the first candidate that is new enough, or { python: null, tried }
// with what was found for each candidate.
function findPython(env, probe = versionOf, platform = process.platform) {
  const tried = [];
  for (const candidate of candidates(env, platform)) {
    const version = probe(candidate);
    if (version && isEnough(version)) {
      return { python: candidate, version };
    }
    tried.push({ candidate, version });
  }
  return { python: null, tried, forced: Boolean(env.NEXORA_PYTHON) };
}

function describeFailure(found) {
  const wanted = MINIMUM.join('.');
  const lines = [`nex: NEXORA needs Python ${wanted} or newer, and none was found.`];
  for (const { candidate, version } of found.tried) {
    const name = [candidate.command, ...candidate.args].join(' ');
    lines.push(version
      ? `  ${name}: is Python ${version.join('.')}, which is too old`
      : `  ${name}: not found, or not a working Python`);
  }
  lines.push(found.forced
    ? 'NEXORA_PYTHON is set, so no other Python was tried. Point it to a Python '
      + `${wanted}+ executable, or unset it.`
    : `Install Python ${wanted}+ from https://www.python.org/downloads/ or set the environment `
      + 'variable NEXORA_PYTHON to the path of a Python executable.');
  return lines.join('\n') + '\n';
}

module.exports = { findPython, describeFailure, candidates, windowsInstallations, isEnough, ENTRY_POINT, NO_PYTHON_EXIT_CODE, MINIMUM };
