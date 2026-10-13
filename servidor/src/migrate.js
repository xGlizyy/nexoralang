// Ejecuta en orden todos los .sql de servidor/migraciones. Son idempotentes (CREATE TABLE IF NOT EXISTS).

import { readdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import mysql from 'mysql2/promise';
import { config } from './config.js';

const dir = fileURLToPath(new URL('../migraciones', import.meta.url));
const files = (await readdir(dir)).filter((file) => file.endsWith('.sql')).sort();

const connection = await mysql.createConnection({ ...config.db, multipleStatements: true });
try {
  for (const file of files) {
    await connection.query(await readFile(path.join(dir, file), 'utf8'));
    console.log(`Aplicada: ${file}`);
  }
} finally {
  await connection.end();
}
