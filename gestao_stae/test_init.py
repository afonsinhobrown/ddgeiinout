import os
os.environ["ORIGEM_CADASTRO"] = "local"

from app import init_pg_db
init_pg_db()
print("Done initializing PG DB without hanging or aborting.")
