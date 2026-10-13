function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Falta la variable de entorno ${name} (revisa servidor/.env)`);
  return value;
}

// Un proveedor sin credenciales queda desactivado: su botón lleva a un aviso en vez de fallar.
function oauthCredentials(prefix) {
  const clientId = process.env[`${prefix}_CLIENT_ID`];
  const clientSecret = process.env[`${prefix}_CLIENT_SECRET`];
  return clientId && clientSecret ? { clientId, clientSecret } : null;
}

const port = Number(process.env.PORT ?? 3000);

export const config = {
  port,
  production: process.env.NODE_ENV === 'production',
  trustProxy: Number(process.env.TRUST_PROXY ?? 0),
  publicUrl: (process.env.PUBLIC_URL ?? `http://localhost:${port}`).replace(/\/+$/, ''),
  db: {
    host: process.env.DB_HOST ?? '127.0.0.1',
    port: Number(process.env.DB_PORT ?? 3306),
    user: required('DB_USER'),
    password: process.env.DB_PASSWORD ?? '',
    database: required('DB_NAME'),
  },
  oauth: {
    google: oauthCredentials('GOOGLE'),
    github: oauthCredentials('GITHUB'),
  },
};
