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
      'A language specification, version 0.6, that describes exactly what the interpreter does.',
      'Eleven accepted design records, each with its reasons, the alternatives it rejected and what it does not guarantee.',
      'A broader design draft of where the language is going.',
    ],
    next: [
      'Lists and `for`, then records and `Option` / `Result`.',
      'Reading input, and modules.',
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
      'More than 1,300 automated tests.',
    ],
    next: [
      'Measuring its speed: it has never been benchmarked.',
      'Checking it on Linux and macOS: so far it is verified on Windows only.',
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
    summary: 'The playground runs real programs; a public repository and published packages are still to come.',
    status: 'in-progress',
    available: [
      'A playground that runs each program with the real interpreter, in a separate process with time and output limits.',
      'Accounts with an email address, and optionally Google or GitHub.',
    ],
    next: [
      'A public repository.',
      'Publishing the packages for npm and Python. The npm package is prepared but not published.',
      'Stronger isolation for the playground, verified on Linux.',
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
