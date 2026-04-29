import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const sessions = sqliteTable('sessions', {
  id: text('id').primaryKey(),
  topic: text('topic').notNull(),
  state: text('state').notNull().default('COMPLETED'),
  config: text('config').notNull(),
  agents: text('agents').notNull(),
  messages: text('messages').notNull(),
  synthesis: text('synthesis'),
  moderatorName: text('moderator_name'),
  createdAt: integer('created_at', { mode: 'timestamp_ms' }).notNull(),
  updatedAt: integer('updated_at', { mode: 'timestamp_ms' }).notNull(),
  expiresAt: integer('expires_at', { mode: 'timestamp_ms' }),
});
