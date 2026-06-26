import sqlite3
import psycopg2
import hashlib
from datetime import datetime
import os

def fix_admin_passwords():
    # Hash for 'admin123'
    new_hash = hashlib.md5("admin123".encode('utf-8')).hexdigest()
    now_str = datetime.now().isoformat()
    
    # Update local SQLite
    s_conn = sqlite3.connect('C:/Users/Acer/Documents/tecnologias/ddgeiinout/gestao_stae/stae.db')
    s_c = s_conn.cursor()
    s_c.execute("UPDATE users SET password = ?, last_modified = ? WHERE username = 'admin'", (new_hash, now_str))
    s_conn.commit()
    s_conn.close()
    
    # Update Cloud PG
    pg_url = "postgresql://neondb_owner:npg_3BsxjEU4NCki@ep-withered-truth-asbeszuu-pooler.c-4.eu-central-1.aws.neon.tech/equipamento?sslmode=require&channel_binding=require"
    try:
        pg_conn = psycopg2.connect(pg_url)
        pg_c = pg_conn.cursor()
        pg_c.execute("UPDATE users SET password = %s, last_modified = %s WHERE username = 'admin'", (new_hash, now_str))
        pg_conn.commit()
        pg_conn.close()
        print("[+] Password para 'admin' foi reposta como 'admin123' em AMBAS as bases de dados (Local e Nuvem).")
    except Exception as e:
        print(f"[-] Erro ao atualizar Nuvem: {e}")

if __name__ == '__main__':
    fix_admin_passwords()
