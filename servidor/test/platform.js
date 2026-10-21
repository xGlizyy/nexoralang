// Lo que el sistema operativo hace por su cuenta, sin que el proyecto lo pida.
//
// Un proceso hijo recibe cosas que no vienen de la configuración del proceso padre: variables que el
// sistema operativo le añade, y un sistema de archivos que puede no distinguir mayúsculas de
// minúsculas. Las pruebas del servidor las tienen en cuenta: una variable de más en el entorno de
// un hijo puede ser una fuga de configuración, y un disco que no distingue la caja cambia qué rutas
// se sirven.

import { existsSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';

// En Windows, libuv (bajo Node) copia del padre estas variables del sistema a todo proceso hijo,
// aunque no se le pasen. No llevan credenciales: son del sistema operativo.
const WINDOWS_CHILD_VARIABLES = Object.freeze([
  'HOMEDRIVE', 'HOMEPATH', 'LOGONSERVER', 'SYSTEMDRIVE', 'TEMP', 'USERDOMAIN', 'USERNAME', 'USERPROFILE', 'WINDIR',
]);
// En macOS, el sistema añade __CF_USER_TEXT_ENCODING a todo proceso nuevo. Tampoco lleva nada del
// padre: es el sistema diciendo en qué codificación está el terminal.
const MACOS_CHILD_VARIABLES = Object.freeze(['__CF_USER_TEXT_ENCODING']);

/**
 * Las variables que el sistema operativo añade a todo proceso hijo en esa plataforma.
 * En otra plataforma, una variable así sería una fuga del entorno del padre, y se rechaza.
 * @param {string} [platform] `process.platform` por defecto.
 * @returns {readonly string[]} Los nombres, en mayúsculas.
 */
export function operatingSystemVariables(platform = process.platform) {
  if (platform === 'win32') return WINDOWS_CHILD_VARIABLES;
  if (platform === 'darwin') return MACOS_CHILD_VARIABLES;
  return [];
}

/**
 * Si el sistema de archivos no distingue mayúsculas de minúsculas, dos nombres que solo se
 * diferencian en la caja son el mismo fichero. Lo hacen Windows y el APFS de macOS por defecto;
 * Linux, no. Se pregunta al disco en vez de suponerlo por el sistema operativo: en macOS el
 * volumen puede ser de las dos clases.
 * @param {string} directory Un directorio en el que se pueda escribir y borrar.
 * @returns {boolean}
 */
export function fileSystemIgnoresCase(directory) {
  // El nombre lleva una mayúscula a propósito: si el disco no distingue la caja, el archivo se
  // encuentra también con el nombre en minúsculas; si la distingue, no.
  const probe = path.join(directory, `.nexora-Mayusculas-${process.pid}`);
  try {
    writeFileSync(probe, '');
    return existsSync(probe.toLowerCase());
  } finally {
    rmSync(probe, { force: true });
  }
}
