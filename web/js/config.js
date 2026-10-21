// Single place for brand settings, external links, roadmap data and the playground runtime.

/**
 * @typedef {'in-progress' | 'planned' | 'done'} PhaseStatus
 * @typedef {{ title: string, summary: string, status: PhaseStatus, available: string[], next: string[] }} Phase
 * @typedef {{ run(source: string): Promise<string> }} PlaygroundRuntime
 */

export const site = {
  name: 'NEXORA',
  /**
   * Public repository URL. While it is null every GitHub link on the site stays hidden,
   * so the site never points to a repository that does not exist.
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
      'A language specification, version 0.9, that describes exactly what the interpreter does.',
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
      '1,604 automated tests. On Linux (Ubuntu 24.04 under WSL 2) all of them pass with Python 3.11, 3.12 and 3.13; on Windows 11 with Python 3.12, 1,600 pass and the 4 that need POSIX are skipped.',
    ],
    next: [
      'Measuring its speed: it has never been benchmarked.',
      'Checking it on macOS and on Linux outside WSL: so far it is verified on Windows 11 and on Ubuntu 24.04 under WSL 2.',
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
    ],
    next: [
      'Editor integration through a language server.',
      'A formatter.',
      'Continuous integration, once the repository is public.',
    ],
  },
  {
    title: 'Playground and ecosystem',
    summary: 'The playground can run real programs but is off by default; a public repository and published packages are still to come.',
    status: 'in-progress',
    available: [
      'A playground that runs each program with the real interpreter, in a separate process with time and output limits. It is off unless the server enables it explicitly.',
      'Accounts with an email address, and optionally Google or GitHub.',
    ],
    next: [
      'A public repository.',
      'Publishing the packages for npm and Python. The npm package is prepared but not published.',
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
