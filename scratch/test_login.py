import hashlib
import psycopg2
pg_url = "postgresql://neondb_owner:npg_3BsxjEU4NCki@ep-withered-truth-asbeszuu-pooler.c-4.eu-central-1.aws.neon.tech/equipamento?sslmode=require&channel_binding=require"
conn = psycopg2.connect(pg_url)
c = conn.cursor()
pwd = hashlib.md5("admin123".encode()).hexdigest()
print("Hash of admin123:", pwd)
c.execute("SELECT * FROM users WHERE username=%s AND password=%s", ("admin", pwd))
res = c.fetchone()
print("Result for admin/admin123:", res)
conn.close()
