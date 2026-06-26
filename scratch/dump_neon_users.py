import psycopg2
pg_url = "postgresql://neondb_owner:npg_3BsxjEU4NCki@ep-withered-truth-asbeszuu-pooler.c-4.eu-central-1.aws.neon.tech/equipamento?sslmode=require&channel_binding=require"
conn = psycopg2.connect(pg_url)
c = conn.cursor()
c.execute("SELECT username FROM users")
print("Neon DB Users:", c.fetchall())
conn.close()
