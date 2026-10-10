import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://kaiki_c_2a0ed6dc8c300eb6ed7abb69:Kk1!aDIinXu119BRTyN_VxO-fxhyMei5@ep-056ebe76c033.kaiki.ru:5432/rubleclicker?sslmode=require"
)

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        salt VARCHAR(64) NOT NULL,
        hash VARCHAR(128) NOT NULL,
        created DOUBLE PRECISION,
        coins BIGINT DEFAULT 0,
        per_click BIGINT DEFAULT 1,
        cps BIGINT DEFAULT 0,
        click_lvl BIGINT DEFAULT 0,
        cps_lvl BIGINT DEFAULT 0,
        level INTEGER DEFAULT 1,
        version INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS tokens (
        token VARCHAR(64) PRIMARY KEY,
        username VARCHAR(50) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
        created DOUBLE PRECISION
    );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ DB init OK")

if __name__ == "__main__":
    init_db()
