import {seal,unseal,now} from './security.mjs';

const tables=new Set(['bco_flows','bco_sessions','bco_exchanges']);
export class Store {
  constructor(db,secret){this.db=db;this.secret=secret;}
  async config(){
    const row=await this.db.prepare("SELECT value FROM bco_config WHERE key='app'").first();
    return row?unseal(row.value,this.secret):null;
  }
  async configure(value){
    await this.db.prepare("INSERT INTO bco_config(key,value) VALUES('app',?)").bind(await seal(value,this.secret)).run();
  }
  async put(table,id,value,expires){
    if(!tables.has(table))throw Error('Invalid store.');
    await this.db.prepare(`INSERT INTO ${table}(id,value,expires) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value,expires=excluded.expires`).bind(id,await seal(value,this.secret),expires).run();
  }
  async get(table,id,consume=false){
    if(!tables.has(table))throw Error('Invalid store.');
    const sql=consume?`DELETE FROM ${table} WHERE id=? RETURNING value,expires`:`SELECT value,expires FROM ${table} WHERE id=?`;
    const row=await this.db.prepare(sql).bind(id).first();
    if(!row || row.expires<=now())return null;
    return {value:await unseal(row.value,this.secret),expires:row.expires};
  }
  async remove(table,id){
    if(!tables.has(table))throw Error('Invalid store.');
    await this.db.prepare(`DELETE FROM ${table} WHERE id=?`).bind(id).run();
  }
  async cleanup(){
    await this.db.batch([...tables].map(table=>this.db.prepare(`DELETE FROM ${table} WHERE expires<=?`).bind(now())));
  }
}
