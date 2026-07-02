import psycopg2
pg_url = "postgresql://neondb_owner:npg_3BsxjEU4NCki@ep-withered-truth-asbeszuu-pooler.c-4.eu-central-1.aws.neon.tech/equipamento?sslmode=require&channel_binding=require"
try:
    conn = psycopg2.connect(pg_url)
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    print("Users in Neon:", users)
    conn.close()
except Exception as e:
    print("Error:", e)
