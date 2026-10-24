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

// The `.py` files of the package and of its subpackages, the directories that have an
// `__init__.py` (the same ones setuptools puts in the wheel, such as `legacy011`). Nothing else
// is copied: no `__pycache__`, no other files.
function copyPackage(from, to, prefix, copied) {
  fs.mkdirSync(to, { recursive: true });
  const entries = fs.readdirSync(from, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1));
  for (const entry of entries) {
    const inner = path.join(from, entry.name);
    if (entry.isFile() && entry.name.endsWith('.py')) {
      fs.copyFileSync(inner, path.join(to, entry.name));
      copied.push(prefix + entry.name);
    } else if (entry.isDirectory() && entry.name !== '__pycache__' && fs.existsSync(path.join(inner, '__init__.py'))) {
      copyPackage(inner, path.join(to, entry.name), `${prefix}${entry.name}/`, copied);
    }
  }
}

fs.rmSync(target, { recursive: true, force: true });
const copied = [];
copyPackage(source, target, '', copied);
fs.copyFileSync(path.join(root, '..', 'LICENSE'), path.join(root, 'LICENSE'));

const versionFile = fs.readFileSync(path.join(source, 'version.py'), 'utf8');
const interpreter = /__version__\s*=\s*"([^"]+)"/.exec(versionFile);
const packageVersion = require(path.join(root, 'package.json')).version;
if (!interpreter || interpreter[1] !== packageVersion) {
  console.error(`sync: package.json says ${packageVersion} but the interpreter is ${interpreter && interpreter[1]}`);
  process.exit(1);
}
console.log(`sync: copied ${copied.length} files of NEXORA ${packageVersion}`);
