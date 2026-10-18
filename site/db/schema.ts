import { sqliteTable, text, primaryKey, index } from "drizzle-orm/sqlite-core";
export const records = sqliteTable("records", {
  kind: text("kind").notNull(), id: text("id").notNull(), body: text("body").notNull(),
  acquiredAt: text("acquired_at"), updatedAt: text("updated_at").notNull(),
}, t => [primaryKey({columns:[t.kind,t.id]}),index("records_acquired").on(t.kind,t.acquiredAt)]);
