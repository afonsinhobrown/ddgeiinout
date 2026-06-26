import psycopg2
import hashlib

pg_url = "postgresql://neondb_owner:npg_3BsxjEU4NCki@ep-withered-truth-asbeszuu-pooler.c-4.eu-central-1.aws.neon.tech/equipamento?sslmode=require&channel_binding=require"
conn = psycopg2.connect(pg_url)
c = conn.cursor()

pwd = hashlib.md5("admin123".encode()).hexdigest()
c.execute("UPDATE users SET password=%s", (pwd,))
conn.commit()
conn.close()
print("Todas as senhas redefinidas para admin123 na nuvem.")
