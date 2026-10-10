import json, os, sys, hashlib, secrets

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

def usage():
    print("""
💰 Админка Рублёвки

  python admin.py list                     все игроки
  python admin.py show <ник>               подробно про игрока
  python admin.py give <ник> <N>           выдать N ₽
  python admin.py take <ник> <N>           забрать N ₽
  python admin.py set <ник> <N>            установить N ₽
  python admin.py level <ник> <N>          уровень монеты 1-100
  python admin.py cps <ник> <N>            ₽/сек
  python admin.py click <ник> <N>          ₽ за тап
  python admin.py reset <ник>              сбросить прогресс
  python admin.py delete <ник>             удалить игрока
  python admin.py password <ник> <newpw>   сменить пароль
""")

def cmd_list(users):
    if not users:
        print("Пока никого нет"); return
    print(f"{'ID':<4} {'НИК':<20} {'₽':<15} {'УР':<5} {'₽/сек':<8}")
    print("-" * 60)
    for k in sorted(users, key=lambda x: users[x].get("id",0)):
        u = users[k]
        print(f"{u.get('id',''):<4} {u.get('username',''):<20} {int(u.get('coins',0)):<15} {u.get('level',1):<5} {int(u.get('cps',0)):<8}")

def cmd_show(users, name):
    u = find(users, name)
    if not u: print(f"❌ {name} не найден"); return
    print(json.dumps({
        "id":u.get("id"), "username":u.get("username"),
        "coins":u.get("coins"), "perClick":u.get("perClick"),
        "cps":u.get("cps"), "clickLvl":u.get("clickLvl"),
        "cpsLvl":u.get("cpsLvl"), "level":u.get("level")
    }, indent=2, ensure_ascii=False))

def get_num(args, idx):
    if len(args) <= idx: return None
    try: return int(args[idx])
    except: return None

def main():
    if len(sys.argv) < 2:
        usage(); return
    cmd = sys.argv[1].lower()
    users = load()

    if cmd == "list":
        cmd_list(users); return

    if len(sys.argv) < 3:
        usage(); return
    name = sys.argv[2].lower()
    u = find(users, name)

    if cmd == "show":
        cmd_show(users, sys.argv[2]); return

    if not u:
        print(f"❌ {name} не найден"); return

    if cmd == "delete":
        del users[name]
        save(users)
        print(f"✅ {u['username']} удалён")
        return

    if cmd == "reset":
        for k in ["coins","perClick","cps","clickLvl","cpsLvl","level"]:
            u[k] = {"coins":0,"perClick":1,"cps":0,"clickLvl":0,"cpsLvl":0,"level":1}[k]
        u["version"] = u.get("version",0) + 1
        save(users)
        print(f"✅ Прогресс {u['username']} сброшен")
        return

    if cmd == "password":
        if len(sys.argv) < 4:
            print("❌ Укажи новый пароль"); return
        newpw = sys.argv[3]
        salt = secrets.token_hex(16)
        u["salt"] = salt
        u["hash"] = hashlib.sha256((salt + newpw).encode()).hexdigest()
        save(users)
        print(f"✅ Пароль {u['username']} изменён")
        return

    n = get_num(sys.argv, 3)
    if n is None:
        print("❌ Укажи число"); return

    if cmd == "give":
        u["coins"] = u.get("coins",0) + n
        print(f"✅ +{n} ₽. Теперь {int(u['coins'])}")
    elif cmd == "take":
        u["coins"] = max(0, u.get("coins",0) - n)
        print(f"✅ -{n} ₽. Теперь {int(u['coins'])}")
    elif cmd == "set":
        u["coins"] = n; print(f"✅ {n} ₽")
    elif cmd == "level":
        u["level"] = max(1, min(100, n)); print(f"✅ Уровень: {u['level']}")
    elif cmd == "cps":
        u["cps"] = n; u["cpsLvl"] = n; print(f"✅ {n} ₽/сек")
    elif cmd == "click":
        u["perClick"] = n; u["clickLvl"] = max(0, n-1); print(f"✅ {n} ₽ за тап")
    else:
        usage(); return

    u["version"] = u.get("version",0) + 1
    save(users)

if __name__ == "__main__":
    main()
