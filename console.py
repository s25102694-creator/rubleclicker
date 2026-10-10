import json, os, sys, hashlib, secrets, time

BASE = os.path.dirname(os.path.abspath(__file__))
USERS = os.path.join(BASE, "data", "users.json")

def load():
    if not os.path.exists(USERS): return {}
    try: return json.load(open(USERS))
    except: return {}

def save(u):
    with open(USERS, "w") as f: json.dump(u, f, indent=2, ensure_ascii=False)

def find(users, name):
    return users.get(name.lower())

def fmt(n):
    n = int(n)
    if n < 1e6: return f"{n:,}".replace(",", " ")
    if n < 1e9: return f"{n/1e6:.2f}M"
    if n < 1e12: return f"{n/1e9:.2f}B"
    return f"{n/1e12:.2f}T"

HELP = """
╔══════════════════════════════════════════════╗
║           💰 КОНСОЛЬ РУБЛЁВКИ                ║
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
║  /delete <ник>             удалить игрока    ║
║  /passwd <ник> <new>       сменить пароль    ║
║  /top                      топ по монетам    ║
║  /help                     эта справка       ║
║  /exit                     выход             ║
╚══════════════════════════════════════════════╝
"""

def cmd_list(users):
    if not users:
        print("📭 Пока никого нет"); return
    print(f"\n{'ID':<4} {'НИК':<20} {'₽':>15} {'УР':>5} {'₽/сек':>8}")
    print("─" * 58)
    for k in sorted(users, key=lambda x: users[x].get("id",0)):
        u = users[k]
        print(f"{u.get('id',''):<4} {u.get('username',''):<20} {fmt(u.get('coins',0)):>15} {u.get('level',1):>5} {int(u.get('cps',0)):>8}")
    print()

def cmd_find(users, name):
    u = find(users, name)
    if not u:
        print(f"❌ {name} не найден"); return
    print(f"""
👤 {u['username']} (ID: {u.get('id')})
💰 Монеты:    {fmt(u.get('coins',0))} ₽
👆 За тап:    {u.get('perClick',1)} ₽
⚡ В сек:     {u.get('cps',0)} ₽/сек
✨ Уровень:   {u.get('level',1)}/100
📅 Создан:    {time.strftime('%d.%m.%Y %H:%M', time.localtime(u.get('created', time.time())))}
""")

def cmd_top(users):
    if not users:
        print("📭 Пусто"); return
    sorted_users = sorted(users.values(), key=lambda x: x.get("coins",0), reverse=True)
    print("\n🏆 ТОП-10:")
    for i, u in enumerate(sorted_users[:10], 1):
        medal = ["🥇","🥈","🥉"][i-1] if i <= 3 else f"{i}."
        print(f"  {medal} {u.get('username','?'):<18} {fmt(u.get('coins',0))} ₽")
    print()

def need_args(args, n):
    if len(args) < n:
        print("❌ Мало аргументов. /help")
        return False
    return True

def get_int(args, idx):
    try: return int(args[idx])
    except: print("❌ Нужно число"); return None

def main():
    print(HELP)
    while True:
        try:
            raw = input("💰 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Пока!")
            break
        if not raw: continue
        if not raw.startswith("/"):
            print("❌ Команды начинаются с /  (напиши /help)")
            continue

        parts = raw[1:].split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:]
        users = load()

        if cmd in ("exit","quit","q"):
            print("👋 Пока!"); break

        elif cmd in ("help","h","?"):
            print(HELP); continue

        elif cmd == "list":
            cmd_list(users)

        elif cmd == "top":
            cmd_top(users)

        elif cmd == "find":
            if not need_args(args,1): continue
            cmd_find(users, args[0])

        elif cmd in ("coins","give"):
            if not need_args(args,2): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            n = get_int(args,1)
            if n is None: continue
            u["coins"] = u.get("coins",0) + n
            u["version"] = u.get("version",0) + 1
            save(users)
            print(f"✅ {u['username']}: +{fmt(n)} ₽ → {fmt(u['coins'])} ₽")

        elif cmd in ("take","remove"):
            if not need_args(args,2): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            n = get_int(args,1)
            if n is None: continue
            u["coins"] = max(0, u.get("coins",0) - n)
            u["version"] = u.get("version",0) + 1
            save(users)
            print(f"✅ {u['username']}: -{fmt(n)} ₽ → {fmt(u['coins'])} ₽")

        elif cmd == "set":
            if not need_args(args,2): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            n = get_int(args,1)
            if n is None: continue
            u["coins"] = n
            u["version"] = u.get("version",0) + 1
            save(users)
            print(f"✅ {u['username']}: {fmt(n)} ₽")

        elif cmd == "level":
            if not need_args(args,2): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            n = get_int(args,1)
            if n is None: continue
            u["level"] = max(1, min(100, n))
            u["version"] = u.get("version",0) + 1
            save(users)
            print(f"✅ {u['username']}: уровень {u['level']}")

        elif cmd == "cps":
            if not need_args(args,2): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            n = get_int(args,1)
            if n is None: continue
            u["cps"] = n; u["cpsLvl"] = n
            u["version"] = u.get("version",0) + 1
            save(users)
            print(f"✅ {u['username']}: {n} ₽/сек")

        elif cmd == "click":
            if not need_args(args,2): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            n = get_int(args,1)
            if n is None: continue
            u["perClick"] = n; u["clickLvl"] = max(0, n-1)
            u["version"] = u.get("version",0) + 1
            save(users)
            print(f"✅ {u['username']}: {n} ₽ за тап")

        elif cmd == "reset":
            if not need_args(args,1): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            u["coins"] = 0; u["perClick"] = 1; u["cps"] = 0
            u["clickLvl"] = 0; u["cpsLvl"] = 0; u["level"] = 1
            u["version"] = u.get("version",0) + 1
            save(users)
            print(f"✅ {u['username']}: прогресс сброшен")

        elif cmd == "delete":
            if not need_args(args,1): continue
            key = args[0].lower()
            if key not in users:
                print(f"❌ {args[0]} не найден"); continue
            name = users[key]["username"]
            if input(f"⚠️  Удалить {name}? (yes/no): ").lower() != "yes":
                print("Отменено"); continue
            del users[key]
            save(users)
            print(f"🗑 {name} удалён")

        elif cmd in ("passwd","password"):
            if not need_args(args,2): continue
            u = find(users, args[0])
            if not u: print(f"❌ {args[0]} не найден"); continue
            salt = secrets.token_hex(16)
            u["salt"] = salt
            u["hash"] = hashlib.sha256((salt + args[1]).encode()).hexdigest()
            save(users)
            print(f"✅ {u['username']}: пароль изменён")

        else:
            print(f"❌ Неизвестная команда: /{cmd}")
            print("   Напиши /help для списка")

if __name__ == "__main__":
    main()
