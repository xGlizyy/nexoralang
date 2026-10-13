#!/usr/bin/env node
'use strict';

// The `nex` command, installed through npm.
//
// NEXORA's interpreter is written in Python. This launcher finds a Python 3.11+ on the
// machine and runs the interpreter bundled in this package with it. It adds nothing to the
// language: arguments, output and exit codes are those of the interpreter.

const { spawn } = require('node:child_process');
const { findPython, describeFailure, ENTRY_POINT, NO_PYTHON_EXIT_CODE } = require('../lib/python.js');

const found = findPython(process.env);
if (!found.python) {
  process.stderr.write(describeFailure(found));
  process.exit(NO_PYTHON_EXIT_CODE);
}

const child = spawn(
  found.python.command,
  [...found.python.args, ENTRY_POINT, ...process.argv.slice(2)],
  { stdio: 'inherit', windowsHide: true },
);

// Ctrl+C reaches the interpreter directly (same terminal); it reports the interruption itself.
process.on('SIGINT', () => {});
process.on('SIGTERM', () => child.kill('SIGTERM'));

child.on('error', (error) => {
  process.stderr.write(`nex: could not start Python (${error.message}).\n`);
  process.exit(NO_PYTHON_EXIT_CODE);
});
child.on('exit', (code, signal) => {
  process.exit(code === null ? (signal === 'SIGINT' ? 130 : 1) : code);
});
