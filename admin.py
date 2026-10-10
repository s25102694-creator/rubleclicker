import json, sys, hashlib, secrets, time
from db import get_db

def find(users, name):
    return users.get(name.lower())

def usage():
    print("""
💰 Админка Рублёвки (PostgreSQL)

  python admin.py list
  python admin.py show <ник>
  python admin.py give <ник> <N>
  python admin.py take <ник> <N>
  python admin.py set <ник> <N>
  python admin.py level <ник> <N>
  python admin.py cps <ник> <N>
  python admin.py click <ник> <N>
  python admin.py reset <ник>
  python admin.py delete <ник>
  python admin.py password <ник> <newpw>
""")

def get_all():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, username, coins, per_click, cps, click_lvl, cps_lvl, level, version FROM users ORDER BY id")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def get_one(name):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, username, coins, per_click, cps, click_lvl, cps_lvl, level, version FROM users WHERE LOWER(username)=LOWER(%s)", (name,))
    r = cur.fetchone()
    cur.close(); conn.close()
    return r

def update(name, **fields):
    conn = get_db(); cur = conn.cursor()
    sets = ", ".join(f"{k}=%s" for k in fields)
    vals = list(fields.values()) + [name]
    cur.execute(f"UPDATE users SET {sets}, version=version+1 WHERE LOWER(username)=LOWER(%s)", vals)
    conn.commit(); cur.close(); conn.close()

def cmd_list():
    rows = get_all()
    if not rows:
        print("Пока никого нет"); return
    print(f"\n{'ID':<4} {'НИК':<20} {'₽':>15} {'УР':>5} {'₽/сек':>8}")
    print("─" * 58)
    for r in rows:
        print(f"{r[0]:<4} {r[1]:<20} {int(r[2]):>15,} {r[7]:>5} {int(r[4]):>8}".replace(",", " "))
    print()

def cmd_show(name):
    u = get_one(name)
    if not u: print(f"❌ {name} не найден"); return
    print(f"""
👤 {u[1]} (ID: {u[0]})
💰 Монеты:    {int(u[2]):,} ₽
👆 За тап:    {u[3]} ₽
⚡ В сек:     {u[4]} ₽/сек
✨ Уровень:   {u[7]}/100
""".replace(",", " "))

def main():
    if len(sys.argv) < 2: usage(); return
    cmd = sys.argv[1].lower()

    if cmd == "list": cmd_list(); return

    if len(sys.argv) < 3: usage(); return
    name = sys.argv[2]
    u = get_one(name)
    if not u and cmd not in ("delete",):
        print(f"❌ {name} не найден"); return

    if cmd == "show": cmd_show(name); return

    if cmd == "delete":
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE LOWER(username)=LOWER(%s)", (name,))
        conn.commit(); cur.close(); conn.close()
        print(f"🗑 {name} удалён"); return

    if cmd == "reset":
        update(name, coins=0, per_click=1, cps=0, click_lvl=0, cps_lvl=0, level=1)
        print(f"✅ {u[1]}: прогресс сброшен"); return

    if cmd == "password":
        if len(sys.argv) < 4: print("❌ Укажи пароль"); return
        newpw = sys.argv[3]
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + newpw).encode()).hexdigest()
        update(name, salt=salt, hash=h)
        print(f"✅ {u[1]}: пароль изменён"); return

    if len(sys.argv) < 4: print("❌ Нужно число"); return
    try: n = int(sys.argv[3])
    except: print("❌ Нужно число"); return

    if cmd == "give":
        update(name, coins=int(u[2])+n); print(f"✅ {u[1]}: +{n:,} ₽".replace(",", " "))
    elif cmd == "take":
        update(name, coins=max(0, int(u[2])-n)); print(f"✅ {u[1]}: -{n:,} ₽".replace(",", " "))
    elif cmd == "set":
        update(name, coins=n); print(f"✅ {u[1]}: {n:,} ₽".replace(",", " "))
    elif cmd == "level":
        update(name, level=max(1, min(100, n))); print(f"✅ {u[1]}: уровень {max(1,min(100,n))}")
    elif cmd == "cps":
        update(name, cps=n, cps_lvl=n); print(f"✅ {u[1]}: {n} ₽/сек")
    elif cmd == "click":
        update(name, per_click=n, click_lvl=max(0, n-1)); print(f"✅ {u[1]}: {n} ₽ за тап")
    else:
        usage()

if __name__ == "__main__":
    main()
