import os
import psycopg2
import psycopg2.extras
import random

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
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tokens (
        token VARCHAR(64) PRIMARY KEY,
        username VARCHAR(50) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
        created DOUBLE PRECISION
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS unions (
        id SERIAL PRIMARY KEY,
        name VARCHAR(40) UNIQUE NOT NULL,
        tag VARCHAR(6) NOT NULL,
        color VARCHAR(16) NOT NULL,
        description VARCHAR(120),
        founder VARCHAR(50),
        created DOUBLE PRECISION
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS union_members (
        username VARCHAR(50) PRIMARY KEY REFERENCES users(username) ON DELETE CASCADE,
        union_id INTEGER NOT NULL REFERENCES unions(id) ON DELETE CASCADE,
        joined DOUBLE PRECISION,
        role VARCHAR(16) DEFAULT 'member'
    );
    """)
    # Миграции — отдельными execute
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS infinite BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE unions ADD COLUMN IF NOT EXISTS closed BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE unions ADD COLUMN IF NOT EXISTS treasury BIGINT DEFAULT 0")
    conn.commit()
    cur.close()
    conn.close()
    print("✅ DB init OK")

ADJ = ["Красный","Золотой","Тёмный","Светлый","Кибер","Стальной","Огненный","Ледяной","Быстрый","Дикий","Синий","Мудрый","Хитрый","Грозный","Тихий","Яростный","Небесный","Подземный","Железный","Бескрайний"]
NOUN = ["Легион","Отряд","Союз","Клан","Орден","Братство","Альянс","Синдикат","Корпорация","Гвардия","Полк","Комитет","Совет","Фронт","Дозор","Патруль","Рейд","Круг","Цех","Союз"]
COLORS = ["#e17076","#7bc862","#e5ca77","#65aadd","#a695e7","#ee7aae","#6ec9cb","#faa774","#ff9d5c","#5fd9c1"]

def seed_unions():
    import time as _t
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM unions")
    if cur.fetchone()[0] >= 15:
        cur.close(); conn.close(); return
    used = set()
    tries = 0
    while len(used) < 15 and tries < 100:
        tries += 1
        n = f"{random.choice(ADJ)} {random.choice(NOUN)}"
        if n in used: continue
        used.add(n)
        tag = "".join(w[0] for w in n.split()[:2]).upper()[:4]
        if len(tag) < 2: tag = (tag + "X")[:3]
        color = random.choice(COLORS)
        try:
            cur.execute(
                "INSERT INTO unions (name, tag, color, description, founder, created, closed, treasury) VALUES (%s,%s,%s,%s,%s,%s,FALSE,0)",
                (n, tag, color, "Союз, основанный игроками", None, _t.time())
            )
        except Exception:
            conn.rollback(); continue
    conn.commit(); cur.close(); conn.close()
    print(f"✅ Засеяно {len(used)} союзов")

if __name__ == "__main__":
    init_db()
    seed_unions()
