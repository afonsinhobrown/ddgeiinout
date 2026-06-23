import sqlite3
import os
import shutil

# Importa a função do próprio sistema para gerar o banco vazio no formato correto
from app import init_db

def migrar():
    if os.path.exists('stae_antigo.db'):
        print("Já existe um backup stae_antigo.db. Abortando para não sobrescrever.")
        return

    # Fazer backup do banco atual
    shutil.copy('stae.db', 'stae_antigo.db')
    print("[+] Backup criado com sucesso: stae_antigo.db")

    # Conectar ao banco antigo para extrair os dados
    conn_old = sqlite3.connect('stae_antigo.db')
    old = conn_old.cursor()

    old.execute("SELECT * FROM users")
    users = old.fetchall()

    old.execute("SELECT * FROM setores")
    setores = old.fetchall()

    old.execute("SELECT * FROM funcionarios")
    funcionarios = old.fetchall()

    old.execute("SELECT * FROM movimentos")
    movimentos = old.fetchall()

    conn_old.close()

    # Apagar banco antigo original para que o init_db crie o novo do zero
    os.remove('stae.db')
    
    # Criar novo banco com as tabelas na versão nova
    init_db()
    
    # Conectar ao novo banco
    conn_new = sqlite3.connect('stae.db')
    new = conn_new.cursor()
    
    # Limpar dados padrão que o init_db pode ter inserido (como admin genérico)
    new.execute("DELETE FROM users")
    new.execute("DELETE FROM sectores")
    new.execute("DELETE FROM sqlite_sequence")
    
    # 1. Migrar Usuários
    for u in users:
        # u = (id, username, password, perfil)
        new.execute("INSERT INTO users (id, username, password, perfil) VALUES (?,?,?,?)", u)
        
    # 2. Migrar Setores
    for s in setores:
        # s = (id, nome)
        new.execute("INSERT INTO sectores (id, nome, tipo) VALUES (?,?,?)", (s[0], s[1], 'interno'))
        
    # 3. Migrar Funcionários
    for f in funcionarios:
        # f = (id, nome, cargo, setor_id)
        new.execute("INSERT INTO funcionarios (id, nome, cargo, sector_id, contacto) VALUES (?,?,?,?,?)", (f[0], f[1], f[2], f[3], ''))
        
    # 4. Migrar Movimentos (e separar equipamentos)
    # Colunas antigas: 0:id, 1:guia, 2:tipo, 3:equipamento, 4:origem_destino, 5:motivo, 6:data, 7:status, 8:tecnico, 9:relatorio, 10:funcionario_id, 11:numero_serie, 12:marca
    for m in movimentos:
        tipo_equip = m[3] if m[3] else "Desconhecido"
        ns = m[11] if m[11] else f"SN-{m[0]}"
        marca = m[12] if m[12] else ""
        
        # Verificar se o equipamento já existe para evitar erro de UNIQUE no numero_serie
        new.execute("SELECT id FROM equipamentos WHERE numero_serie=?", (ns,))
        eq = new.fetchone()
        if eq:
            equip_id = eq[0]
        else:
            new.execute("INSERT INTO equipamentos (numero_serie, patrimonio, tipo, marca, modelo, estado, observacoes) VALUES (?,?,?,?,?,?,?)",
                        (ns, "", tipo_equip, marca, "", m[7], ""))
            equip_id = new.lastrowid
            
        # Inserir o movimento adaptado para a nova estrutura
        new.execute('''INSERT INTO movimentos 
            (id, numero_guia, tipo, equipamento_id, quantidade, origem_destino, motivo, data_movimento, status, relatorio_reparacao, tecnico_responsavel, funcionario_entrega_id, observacao) 
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
            (m[0], m[1], m[2], equip_id, 1, m[4], m[5], m[6], m[7], m[9], m[8], m[10], ""))
            
    conn_new.commit()
    conn_new.close()
    print("[+] Migração concluída com sucesso! Todos os seus dados estão na nova versão.")

if __name__ == '__main__':
    migrar()
