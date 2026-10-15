// Single place for brand settings, external links, roadmap data and the playground runtime.

/**
 * @typedef {'in-progress' | 'planned' | 'done'} PhaseStatus
 * @typedef {{ title: string, description: string, status: PhaseStatus }} Phase
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

/** @type {Phase[]} */
export const roadmap = [
  {
    title: 'Language design',
    description: 'A specification (version 0.5) describes exactly what the interpreter does, and ten design records explain each decision. Operations on text, collections and modules are still to come, and the syntax can still change.',
    status: 'in-progress',
  },
  {
    title: 'First interpreter',
    description: 'A reference interpreter in Python, version 0.5: static types, functions, conditions, loops that declare why they end, contracts, refined types and examples checked with nex test. More than 1,300 automated tests check it.',
    status: 'done',
  },
  {
    title: 'Tooling and documentation',
    description: 'The nex command runs, checks and tests programs, and describes them as versioned JSON for editors and AI agents. An optional MCP server is experimental, and there is no editor integration yet.',
    status: 'in-progress',
  },
  {
    title: 'Playground and ecosystem',
    description: 'The playground runs each program with the real interpreter, in a separate process with time and output limits. A public repository and published packages do not exist yet.',
    status: 'in-progress',
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
