// Cómo se describe un error en el registro del servidor sin copiar sus datos.
//
// Un error puede llevar mucho más que su tipo: los de MySQL traen la consulta y el mensaje del
// servidor («Duplicate entry 'ana@example.com'…»), y uno de fetch puede llevar una URL. Por eso el
// registro nunca recibe el objeto entero, ni su mensaje, ni su pila: solo el tipo y un código conocido
// (ECONNREFUSED, ER_DUP_ENTRY, provider_http_500…), y solo si tienen la forma de un identificador.

const NAME = /^[A-Za-z][A-Za-z0-9]{0,39}$/;
const CODE = /^[A-Za-z0-9_.-]{1,64}$/;

/** «TypeError», «Error ECONNREFUSED», «Error ER_DUP_ENTRY»: el tipo y el código, nada más. */
export function describeError(error) {
  if (!(error instanceof Error)) return 'non-error value';
  const name = NAME.test(error.name) ? error.name : 'Error';
  const { code } = error;
  if (typeof code === 'number' && Number.isInteger(code)) return `${name} ${code}`;
  return typeof code === 'string' && CODE.test(code) ? `${name} ${code}` : name;
}

/**
 * La ruta de una petición para el registro: la PLANTILLA de Express (el montaje y la ruta tal como
 * están escritos en el código, «/api/auth/:provider/callback»), nunca el camino pedido, la URL ni la
 * cadena de consulta, que escribe quien hace la petición. Hay que llamarla donde baseUrl todavía es
 * el del montaje (app.js lo hace en un manejador de errores de cada montaje). Sin una ruta escrita
 * como texto que haya coincidido, devuelve un valor fijo.
 */
export function describeRoute(req) {
  const path = req?.route?.path;
  if (typeof path !== 'string') return '(no route)';
  // baseUrl es la parte de la URL que coincidió con el montaje: el texto del código, salvo las
  // mayúsculas, que Express no distingue y copia de la petición. Vale porque los montajes de app.js
  // son textos fijos; un montaje con parámetros («/u/:id») pondría aquí los valores pedidos.
  const base = typeof req.baseUrl === 'string' ? req.baseUrl.toLowerCase() : '';
  return `${base}${path}`.slice(0, 80).replace(/[^\w/:.-]/g, '_');
}
