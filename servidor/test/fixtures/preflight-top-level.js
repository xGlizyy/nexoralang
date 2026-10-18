// Para preflight-probe.js: un módulo que importa servidor/src/ con await a nivel superior, al cargarse.
export const config = await import('../../src/config.js');
