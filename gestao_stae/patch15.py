import os
import re
from app import get_pg_connection, DB_PATH

def patch_app_py():
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    pg_trigger_code = """
        # Create trigger function for PG
        try:
            c.execute('''
                CREATE OR REPLACE FUNCTION update_last_modified_column()
                RETURNS TRIGGER AS $$
                BEGIN
                   NEW.last_modified = to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS');
                   RETURN NEW;
                END;
                $$ language 'plpgsql';
            ''')
        except Exception as ex:
            print(f"[-] Erro ao criar funcao de trigger no PG: {ex}")
            
        for t in tables:
            try:
                c.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS last_modified VARCHAR DEFAULT '2026-06-24T00:00:00'")
            except Exception as ex:
                print(f"[-] Erro ao migrar last_modified no PG para {t}: {ex}")
            try:
                c.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS origem_registo VARCHAR DEFAULT 'local'")
            except Exception as ex:
                print(f"[-] Erro ao migrar origem_registo no PG para {t}: {ex}")
                
            try:
                c.execute(f'''
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'tr_update_last_modified_{t}') THEN
                            CREATE TRIGGER tr_update_last_modified_{t}
                            BEFORE UPDATE ON {t}
                            FOR EACH ROW
                            WHEN (NEW.last_modified IS NULL OR NEW.last_modified = OLD.last_modified)
                            EXECUTE FUNCTION update_last_modified_column();
                        END IF;
                    END
                    $$;
                ''')
            except Exception as ex:
                print(f"[-] Erro ao criar trigger no PG para {t}: {ex}")
"""
    
    # Replace the loop in init_pg_db
    pattern = r"for t in tables:\s+try:\s+c\.execute\(f\"ALTER TABLE \{t\} ADD COLUMN IF NOT EXISTS last_modified.*?(?=try:\s+c\.execute\(\"ALTER TABLE users ADD COLUMN IF NOT EXISTS setor_id)"
    
    # Check if we already patched it
    if "CREATE OR REPLACE FUNCTION update_last_modified_column" not in content:
        content = re.sub(pattern, pg_trigger_code, content, flags=re.DOTALL)
        with open('app.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("app.py patched with PG triggers!")
    else:
        print("app.py already has PG triggers.")

def apply_pg_triggers_now():
    conn = get_pg_connection()
    if not conn:
        print("PG inacessivel.")
        return
    c = conn.cursor()
    c.execute('''
        CREATE OR REPLACE FUNCTION update_last_modified_column()
        RETURNS TRIGGER AS $$
        BEGIN
           NEW.last_modified = to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS');
           RETURN NEW;
        END;
        $$ language 'plpgsql';
    ''')
    
    tables = ['users', 'setores', 'funcionarios', 'movimentos', 'marcas', 'tipos_equipamento', 'motivos', 'fornecedores', 'instituicoes', 'inventario_local']
    for t in tables:
        c.execute(f'''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'tr_update_last_modified_{t}') THEN
                    CREATE TRIGGER tr_update_last_modified_{t}
                    BEFORE UPDATE ON {t}
                    FOR EACH ROW
                    WHEN (NEW.last_modified IS NULL OR NEW.last_modified = OLD.last_modified)
                    EXECUTE FUNCTION update_last_modified_column();
                END IF;
            END
            $$;
        ''')
    conn.commit()
    conn.close()
    print("PG triggers applied to database successfully.")

if __name__ == '__main__':
    patch_app_py()
    apply_pg_triggers_now()
