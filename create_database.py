import os
import sys
import time

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


admin_user = os.getenv("DEFAULT_ADMIN_USER", "postgres")
admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "postgres")
admin_db = os.getenv("DEFAULT_ADMIN_DB", "postgres")

host = os.getenv("PG__HOST", "postgres")
port = int(os.getenv("PG__PORT", "5432"))

user = os.getenv("PG__USER")
password = os.getenv("PG__PASSWORD")
database = os.getenv("PG__DATABASE")


if not user or not password or not database:
    print("PG__USER, PG__PASSWORD и PG__DATABASE обязательны", file=sys.stderr)
    sys.exit(1)


def connect(dbname: str = "postgres"):
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=admin_user,
        password=admin_password,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


for _ in range(60):
    try:
        conn = connect(admin_db)
        break
    except psycopg2.OperationalError:
        time.sleep(1)
else:
    raise RuntimeError("PostgreSQL is not available")


cur = conn.cursor()

cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
role_exists = cur.fetchone() is not None

if role_exists:
    cur.execute(
        sql.SQL("ALTER USER {} WITH PASSWORD %s").format(sql.Identifier(user)),
        (password,),
    )
    print(f"User {user} already exists, password updated")
else:
    cur.execute(
        sql.SQL("CREATE USER {} WITH PASSWORD %s").format(sql.Identifier(user)),
        (password,),
    )
    print(f"Created user {user}")


cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
db_exists = cur.fetchone() is not None

if db_exists:
    print(f"Database {database} already exists")
else:
    cur.execute(
        sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(database),
            sql.Identifier(user),
        )
    )
    print(f"Created database {database}")


cur.close()
conn.close()


conn = connect(database)
cur = conn.cursor()

cur.execute(
    sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
        sql.Identifier(database),
        sql.Identifier(user),
    )
)

cur.execute(
    sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
        sql.Identifier(database),
        sql.Identifier(user),
    )
)

cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

cur.execute(
    sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(
        sql.Identifier(user),
    )
)

cur.execute(
    sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {}").format(
        sql.Identifier(user),
    )
)

cur.close()
conn.close()

print("Database and permissions are ready")