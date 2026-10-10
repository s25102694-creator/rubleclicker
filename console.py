from db import get_db
import hashlib, secrets

HELP = """
╔══════════════════════════════════════════════╗
║        💰 КОНСОЛЬ РУБЛЁВКИ (PostgreSQL)      ║
╠══════════════════════════════════════════════╣
║  /list                     все игроки        ║
║  /find <ник>               детали игрока     ║
║  /coins <ник> <N>          выдать N ₽        ║
║  /take <ник> <N>           забрать N ₽       ║
║  /set <ник> <N>            установить N ₽    ║
║  /level <ник> <N>          уровень 1-100     ║
║  /cps <ник> <N>            ₽/сек             ║
║  /click <ник> <N>          ₽ за тап          ║
║  /reset <ник>              сбросить прогресс ║
║  /infinite <ник>           ∞ монеты (вкл)   ║
║  /finite <ник>             выключить ∞       ║
║  /god <ник>                всё на максимум   ║
║  /delete <ник>             удалить игрока    ║
║  /passwd <ник> <new>       сменить пароль    ║
║  /top                      топ по монетам    ║
║  /text <сообщение>         всем на экран     ║
║  /help                     эта справка       ║
║  /exit                     выход             ║
╚══════════════════════════════════════════════╝
"""

def fmt(n):
    n = int(n)
    return f"{n:,}".replace(",", " ")

def get_one(name):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, username, coins, per_click, cps, click_lvl, cps_lvl, level, version FROM users WHERE LOWER(username)=LOWER(%s)", (name,))
    r = cur.fetchone(); cur.close(); conn.close()
    return r

def update(name, **fields):
    conn = get_db(); cur = conn.cursor()
    sets = ", ".join(f"{k}=%s" for k in fields)
    vals = list(fields.values()) + [name]
    cur.execute(f"UPDATE users SET {sets}, version=version+1 WHERE LOWER(username)=LOWER(%s)", vals)
    conn.commit(); cur.close(); conn.close()

def cmd_list():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, username, coins, cps, level FROM users ORDER BY id")
    rows = cur.fetchall(); cur.close(); conn.close()
    if not rows: print("📭 Пока никого нет"); return
    print(f"\n{'ID':<4} {'НИК':<20} {'₽':>15} {'УР':>5} {'₽/сек':>8}")
    print("─" * 58)
    for r in rows:
        print(f"{r[0]:<4} {r[1]:<20} {fmt(r[2]):>15} {r[4]:>5} {int(r[3]):>8}")
    print()

def cmd_top():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT 10")
    rows = cur.fetchall(); cur.close(); conn.close()
    if not rows: print("📭 Пусто"); return
    print("\n🏆 ТОП-10:")
    for i, r in enumerate(rows, 1):
        medal = ["🥇","🥈","🥉"][i-1] if i <= 3 else f"{i}."
        print(f"  {medal} {r[0]:<18} {fmt(r[1])} ₽")
    print()

def cmd_find(name):
    u = get_one(name)
    if not u: print(f"❌ {name} не найден"); return
    print(f"""
👤 {u[1]} (ID: {u[0]})
💰 Монеты:    {fmt(u[2])} ₽
👆 За тап:    {u[3]} ₽
⚡ В сек:     {u[4]} ₽/сек
✨ Уровень:   {u[7]}/100
""")

def main():
    print(HELP)
    while True:
        try:
            raw = input("💰 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Пока!"); break
        if not raw: continue
        if not raw.startswith("/"):
            print("❌ Команды начинаются с /"); continue
        parts = raw[1:].split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:]

        try:
            if cmd in ("exit","quit","q"):
                print("👋 Пока!"); break
            elif cmd in ("help","h","?"): print(HELP)
            elif cmd == "list": cmd_list()
            elif cmd == "top": cmd_top()
            elif cmd == "find":
                if len(args) < 1: print("❌ /find <ник>"); continue
                cmd_find(args[0])
            elif cmd in ("infinite","finite","god"):
                if len(args) < 1: print(f"❌ /{cmd} <ник>"); continue
                name = args[0]; u = get_one(name)
                if not u: print(f"❌ {name} не найден"); continue
                if cmd == "infinite":
                    update(name, infinite=True)
                    print(f"♾️  {u[1]}: бесконечные монеты ВКЛ")
                elif cmd == "finite":
                    update(name, infinite=False)
                    print(f"🔒 {u[1]}: бесконечные монеты ВЫКЛ")
                elif cmd == "god":
                    update(name, infinite=True, per_click=9999999, cps=9999999,
                           click_lvl=200, cps_lvl=200, level=120)
                    print(f"⚡ {u[1]}: GOD MODE — ∞ + всё на максимум")
            elif cmd in ("coins","give","take","set","level","cps","click","reset"):
                if cmd != "reset" and len(args) < 2: print("❌ мало аргументов"); continue
                if cmd == "reset" and len(args) < 1: print("❌ /reset <ник>"); continue
                name = args[0]; u = get_one(name)
                if not u: print(f"❌ {name} не найден"); continue
                if cmd == "reset":
                    update(name, coins=0, per_click=1, cps=0, click_lvl=0, cps_lvl=0, level=1)
                    print(f"✅ {u[1]}: прогресс сброшен"); continue
                try: n = int(args[1])
                except: print("❌ нужно число"); continue
                if cmd in ("coins","give"):
                    update(name, coins=int(u[2])+n); print(f"✅ {u[1]}: +{fmt(n)} ₽ → {fmt(int(u[2])+n)} ₽")
                elif cmd == "take":
                    new = max(0, int(u[2])-n); update(name, coins=new); print(f"✅ {u[1]}: -{fmt(n)} ₽ → {fmt(new)} ₽")
                elif cmd == "set":
                    update(name, coins=n); print(f"✅ {u[1]}: {fmt(n)} ₽")
                elif cmd == "level":
                    v = max(1,min(100,n)); update(name, level=v); print(f"✅ {u[1]}: уровень {v}")
                elif cmd == "cps":
                    update(name, cps=n, cps_lvl=n); print(f"✅ {u[1]}: {n} ₽/сек")
                elif cmd == "click":
                    update(name, per_click=n, click_lvl=max(0,n-1)); print(f"✅ {u[1]}: {n} ₽ за тап")
            elif cmd == "text":
                if len(args) < 1: print("❌ /text <сообщение>"); continue
                msg = " ".join(args)[:200]
                import time as _t
                conn = get_db(); cur = conn.cursor()
                cur.execute("INSERT INTO broadcasts (text, author, created, expires) VALUES (%s,%s,%s,%s)",
                            (msg, "admin", _t.time(), _t.time() + 60))
                conn.commit(); cur.close(); conn.close()
                print(f"📢 Отправлено всем: {msg}")
            elif cmd == "delete":
                if len(args) < 1: print("❌ /delete <ник>"); continue
                name = args[0]; u = get_one(name)
                if not u: print(f"❌ {name} не найден"); continue
                if input(f"⚠️  Удалить {u[1]}? (yes/no): ").lower() != "yes": continue
                conn = get_db(); cur = conn.cursor()
                cur.execute("DELETE FROM users WHERE LOWER(username)=LOWER(%s)", (name,))
                conn.commit(); cur.close(); conn.close()
                print(f"🗑 {u[1]} удалён")
            elif cmd in ("passwd","password"):
                if len(args) < 2: print("❌ /passwd <ник> <new>"); continue
                name = args[0]; u = get_one(name)
                if not u: print(f"❌ {name} не найден"); continue
                salt = secrets.token_hex(16)
                h = hashlib.sha256((salt + args[1]).encode()).hexdigest()
                update(name, salt=salt, hash=h)
                print(f"✅ {u[1]}: пароль изменён")
            else:
                print(f"❌ Неизвестная: /{cmd}")
        except Exception as e:
            print(f"💥 Ошибка: {e}")

if __name__ == "__main__":
    main()
