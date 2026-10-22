// Single place for brand settings, external links, roadmap data and the playground runtime.

/**
 * @typedef {'in-progress' | 'planned' | 'done'} PhaseStatus
 * @typedef {{ title: string, summary: string, status: PhaseStatus, available: string[], next: string[] }} Phase
 * @typedef {{ run(source: string): Promise<string> }} PlaygroundRuntime
 */

export const site = {
  name: 'NEXORA',
  /**
   * Public repository URL. While it is null every GitHub link on the site stays hidden:
   * the site does not send anyone to the repository.
   * @type {string | null}
   */
  githubUrl: null,
};

/**
 * The phases of the project. `summary` is one sentence, shown everywhere; `available` and `next`
 * are shown in the documentation. Only facts that can be checked in the repository go here.
 * Text between backticks is shown as code.
 * @type {Phase[]}
 */
export const roadmap = [
  {
    title: 'Language design',
    summary: 'The rules are written down before they are built, and the specification follows the interpreter exactly. The syntax can still change.',
    status: 'in-progress',
    available: [
      'A language specification, version 0.10, that describes exactly what the interpreter does.',
      'Fourteen accepted design records, each with its reasons, the alternatives it rejected and what it does not guarantee.',
      'A broader design draft of where the language is going.',
      'Lists and `for` (0.7.0), and records (0.8.0): the first compound types of the language.',
      'Arguments, standard input and files with explicit permissions (0.9.0).',
    ],
    next: [
      'Optional values (`Option`, `Result`), for the absence of a value and for errors without exceptions.',
      'Modules and imports.',
    ],
  },
  {
    title: 'First interpreter',
    summary: 'A reference interpreter in Python runs every program the specification describes.',
    status: 'done',
    available: [
      'Static types (`Int`, `Float`, `Bool`, `Text`) with no implicit conversions.',
      'Functions, `if`, `let` and `var`, and `while` loops that declare why they end.',
      'Contracts (`requires`, `ensures`), refined types and examples checked with `nex test`.',
      'Operations on text (`Text.length`, `Text.slice`, ordering) and reading numbers with `Int.parse`, each with the requirements it checks.',
      'Diagnostics with a stable code, a position and a hint, as text or JSON.',
      '2,329 automated tests. The continuous integration runs them on Linux, Windows and macOS with Python 3.11, 3.12 and 3.13, and the ones a platform cannot run are skipped there.',
    ],
    next: [
      'Measuring its speed: it has never been benchmarked.',
      'Checking it on a real Mac and on Linux outside WSL: so far the continuous integration verifies it on Linux, Windows and macOS, and it has been run by hand on Windows 11 with Python 3.12 and on Ubuntu 24.04 under WSL 2.',
    ],
  },
  {
    title: 'Tooling and documentation',
    summary: 'The `nex` command and versioned JSON formats let people, editors and AI agents work with programs.',
    status: 'in-progress',
    available: [
      '`nex run`, `nex check` and `nex test`.',
      '`nex inspect`, `nex symbols` and `nex context`: the program as versioned JSON, with a schema for each format.',
      'A language guide, a full reference and this documentation.',
      'An optional MCP server for AI assistants. It is experimental.',
      'Continuous integration: every change to `main` runs the tests on Linux, Windows and macOS, with Python 3.11 to 3.13, and the tests of the npm package and of the server.',
    ],
    next: [
      'Editor integration through a language server.',
      'A formatter.',
    ],
  },
  {
    title: 'Playground and ecosystem',
    summary: 'The playground can run real programs but is off by default; the repository is public and the npm package is published.',
    status: 'in-progress',
    available: [
      'A playground that runs each program with the real interpreter, in a separate process with time and output limits. It is off unless the server enables it explicitly.',
      'Accounts with an email address, and optionally Google or GitHub.',
      'A public repository, with its history and its issue tracker.',
    ],
    next: [
      'Publishing the Python package on PyPI. The npm package is published.',
      'Checking the isolation of the playground containers with real Docker. Until then it stays off on a public site.',
    ],
  },
];

/** @type {Record<PhaseStatus, string>} */
export const statusLabels = {
  'in-progress': 'In progress',
  planned: 'Planned',
  done: 'Done',
};

/**
 * Interpreter used by the playground. Null until a real interpreter exists;
 * the playground then stays in preview mode and never pretends to run code.
 * @type {PlaygroundRuntime | null}
 */
export const playgroundRuntime = null;
