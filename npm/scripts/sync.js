'use strict';

// Copies the interpreter from nexora/src/nexora into this package (python/nexora), together
// with the licence, and checks that the versions agree. It runs before `npm pack`,
// `npm publish` and the tests, so the package always carries the current interpreter.
// The copy is not kept in git.

const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const source = path.join(root, '..', 'nexora', 'src', 'nexora');
const target = path.join(root, 'python', 'nexora');

if (!fs.existsSync(source)) {
  // Installed from the registry: the copy is already inside the package.
  if (fs.existsSync(target)) {
    process.exit(0);
  }
  console.error(`sync: cannot find the interpreter at ${source}`);
  process.exit(1);
}

fs.rmSync(target, { recursive: true, force: true });
fs.mkdirSync(target, { recursive: true });
const copied = [];
for (const name of fs.readdirSync(source).sort()) {
  if (name.endsWith('.py')) {
    fs.copyFileSync(path.join(source, name), path.join(target, name));
    copied.push(name);
  }
}
fs.copyFileSync(path.join(root, '..', 'LICENSE'), path.join(root, 'LICENSE'));

const versionFile = fs.readFileSync(path.join(source, 'version.py'), 'utf8');
const interpreter = /__version__\s*=\s*"([^"]+)"/.exec(versionFile);
const packageVersion = require(path.join(root, 'package.json')).version;
if (!interpreter || interpreter[1] !== packageVersion) {
  console.error(`sync: package.json says ${packageVersion} but the interpreter is ${interpreter && interpreter[1]}`);
  process.exit(1);
}
console.log(`sync: copied ${copied.length} files of NEXORA ${packageVersion}`);
