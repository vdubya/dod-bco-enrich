import {sqliteTable,text,integer,index} from 'drizzle-orm/sqlite-core';

export const appConfig=sqliteTable('bco_config',{key:text('key').primaryKey(),value:text('value').notNull()});
export const flows=sqliteTable('bco_flows',{
  id:text('id').primaryKey(),value:text('value').notNull(),expires:integer('expires').notNull()
},table=>[index('idx_bco_flows_expires').on(table.expires)]);
export const sessions=sqliteTable('bco_sessions',{
  id:text('id').primaryKey(),value:text('value').notNull(),expires:integer('expires').notNull()
},table=>[index('idx_bco_sessions_expires').on(table.expires)]);
export const exchanges=sqliteTable('bco_exchanges',{
  id:text('id').primaryKey(),value:text('value').notNull(),expires:integer('expires').notNull()
},table=>[index('idx_bco_exchanges_expires').on(table.expires)]);
