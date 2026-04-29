import { drizzle } from 'drizzle-orm/d1';
import * as schema from './schema';

export type Database = typeof schema;

export function getDb(env: { DB: D1Database }) {
  return drizzle(env.DB, { schema });
}

export { sessions } from './schema';
