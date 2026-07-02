import sqlite3
import os
from app import DB_PATH, get_pg_connection

def fix_app_code():
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()

    old_func = """def sync_inventario_local():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    s_c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo FROM inventario_local")
    s_items = {}
    for r in s_c.fetchall():
        key = f"{r[0]}::{r[1]}::{r[2]}"
        s_items[key] = {
            'equipamento': r[0], 'marca': r[1], 'numero_serie': r[2], 'quantidade': r[3], 'status': r[4],
            'data_registo': r[5], 'observacoes': r[6], 'last_modified': r[7], 'origem_registo': r[8]
        }
        
    pg_conn = get_pg_connection()
    if not pg_conn:
        s_conn.close()
        return False
    pg_c = pg_conn.cursor()
    pg_c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo FROM inventario_local")
    pg_items = {}
    for r in pg_c.fetchall():
        key = f"{r[0]}::{r[1]}::{r[2]}"
        pg_items[key] = {
            'equipamento': r[0], 'marca': r[1], 'numero_serie': r[2], 'quantidade': r[3], 'status': r[4],
            'data_registo': r[5], 'observacoes': r[6], 'last_modified': r[7], 'origem_registo': r[8]
        }
        
    for key, s_i in s_items.items():
        if key not in pg_items:
            pg_c.execute('''INSERT INTO inventario_local 
                (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (s_i['equipamento'], s_i['marca'], s_i['numero_serie'], s_i['quantidade'], s_i['status'], s_i['data_registo'], s_i['observacoes'], s_i['last_modified'], s_i['origem_registo']))
        elif s_i['last_modified'] > pg_items[key]['last_modified']:
            pg_c.execute('''UPDATE inventario_local SET 
                quantidade=%s, status=%s, data_registo=%s, observacoes=%s, last_modified=%s, origem_registo=%s 
                WHERE equipamento=%s AND marca=%s AND numero_serie=%s''',
                (s_i['quantidade'], s_i['status'], s_i['data_registo'], s_i['observacoes'], s_i['last_modified'], s_i['origem_registo'], s_i['equipamento'], s_i['marca'], s_i['numero_serie']))
                
    for key, pg_i in pg_items.items():
        if key not in s_items:
            s_c.execute('''INSERT INTO inventario_local 
                (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo) 
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (pg_i['equipamento'], pg_i['marca'], pg_i['numero_serie'], pg_i['quantidade'], pg_i['status'], pg_i['data_registo'], pg_i['observacoes'], pg_i['last_modified'], pg_i['origem_registo']))
        elif pg_i['last_modified'] > s_items[key]['last_modified']:
            s_c.execute('''UPDATE inventario_local SET 
                quantidade=?, status=?, data_registo=?, observacoes=?, last_modified=?, origem_registo=? 
                WHERE equipamento=? AND marca=? AND numero_serie=?''',
                (pg_i['quantidade'], pg_i['status'], pg_i['data_registo'], pg_i['observacoes'], pg_i['last_modified'], pg_i['origem_registo'], pg_i['equipamento'], pg_i['marca'], pg_i['numero_serie']))
                
    pg_conn.commit()
    pg_conn.close()
    s_conn.commit()
    s_conn.close()
    return True"""

    new_func = """def sync_inventario_local():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    s_c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id FROM inventario_local")
    s_items = {}
    for r in s_c.fetchall():
        key = f"{r[0]}::{r[1]}::{r[2]}"
        s_items[key] = {
            'equipamento': r[0], 'marca': r[1], 'numero_serie': r[2], 'quantidade': r[3], 'status': r[4],
            'data_registo': r[5], 'observacoes': r[6], 'last_modified': r[7], 'origem_registo': r[8], 'setor_id': r[9]
        }
        
    pg_conn = get_pg_connection()
    if not pg_conn:
        s_conn.close()
        return False
    pg_c = pg_conn.cursor()
    pg_c.execute("SELECT equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id FROM inventario_local")
    pg_items = {}
    for r in pg_c.fetchall():
        key = f"{r[0]}::{r[1]}::{r[2]}"
        pg_items[key] = {
            'equipamento': r[0], 'marca': r[1], 'numero_serie': r[2], 'quantidade': r[3], 'status': r[4],
            'data_registo': r[5], 'observacoes': r[6], 'last_modified': r[7], 'origem_registo': r[8], 'setor_id': r[9]
        }
        
    for key, s_i in s_items.items():
        if key not in pg_items:
            pg_c.execute('''INSERT INTO inventario_local 
                (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (s_i['equipamento'], s_i['marca'], s_i['numero_serie'], s_i['quantidade'], s_i['status'], s_i['data_registo'], s_i['observacoes'], s_i['last_modified'], s_i['origem_registo'], s_i['setor_id']))
        elif s_i['last_modified'] > pg_items[key]['last_modified']:
            pg_c.execute('''UPDATE inventario_local SET 
                quantidade=%s, status=%s, data_registo=%s, observacoes=%s, last_modified=%s, origem_registo=%s, setor_id=%s 
                WHERE equipamento=%s AND marca=%s AND numero_serie=%s''',
                (s_i['quantidade'], s_i['status'], s_i['data_registo'], s_i['observacoes'], s_i['last_modified'], s_i['origem_registo'], s_i['setor_id'], s_i['equipamento'], s_i['marca'], s_i['numero_serie']))
                
    for key, pg_i in pg_items.items():
        if key not in s_items:
            s_c.execute('''INSERT INTO inventario_local 
                (equipamento, marca, numero_serie, quantidade, status, data_registo, observacoes, last_modified, origem_registo, setor_id) 
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (pg_i['equipamento'], pg_i['marca'], pg_i['numero_serie'], pg_i['quantidade'], pg_i['status'], pg_i['data_registo'], pg_i['observacoes'], pg_i['last_modified'], pg_i['origem_registo'], pg_i['setor_id']))
        elif pg_i['last_modified'] > s_items[key]['last_modified']:
            s_c.execute('''UPDATE inventario_local SET 
                quantidade=?, status=?, data_registo=?, observacoes=?, last_modified=?, origem_registo=?, setor_id=? 
                WHERE equipamento=? AND marca=? AND numero_serie=?''',
                (pg_i['quantidade'], pg_i['status'], pg_i['data_registo'], pg_i['observacoes'], pg_i['last_modified'], pg_i['origem_registo'], pg_i['setor_id'], pg_i['equipamento'], pg_i['marca'], pg_i['numero_serie']))
                
    pg_conn.commit()
    pg_conn.close()
    s_conn.commit()
    s_conn.close()
    return True"""

    content = content.replace(old_func, new_func)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Code patched.")

def fix_database():
    s_conn = sqlite3.connect(DB_PATH)
    s_c = s_conn.cursor()
    
    # Check if there are null sectors in inventario
    s_c.execute("UPDATE inventario_local SET setor_id = 1 WHERE setor_id IS NULL")
    
    s_conn.commit()
    s_conn.close()
    
    # Also update Postgres
    pg_conn = get_pg_connection()
    if pg_conn:
        pg_c = pg_conn.cursor()
        pg_c.execute("UPDATE inventario_local SET setor_id = 1 WHERE setor_id IS NULL")
        pg_conn.commit()
        pg_conn.close()
        
    print("Database data fixed. All unassigned equipment is now in sector 1.")

if __name__ == '__main__':
    fix_app_code()
    fix_database()
