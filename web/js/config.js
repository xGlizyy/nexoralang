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
    description: 'Define the syntax and the rules of the language. A first specification exists; the language is still small and changing.',
    status: 'in-progress',
  },
  {
    title: 'First interpreter',
    description: 'A reference interpreter runs a subset of the language: types, functions, conditions, loops that declare why they end, contracts, refined types and examples checked with nex test.',
    status: 'done',
  },
  {
    title: 'Tooling and documentation',
    description: 'A command-line tool, guides and a language reference exist. More tools are still to come.',
    status: 'in-progress',
  },
  {
    title: 'Playground and ecosystem',
    description: 'A first playground runs code in the browser with the real interpreter. The ecosystem around the language is still to come.',
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
