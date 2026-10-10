from flask import Flask, request, jsonify, render_template
import secrets, hashlib, time, psycopg2
from psycopg2.extras import RealDictCursor
from db import get_db, init_db

app = Flask(__name__)

try:
    init_db()
except Exception as e:
    print("DB init error:", e)

def hash_pw(pw, salt=None):
    if salt is None: salt = secrets.token_hex(16)
    return salt, hashlib.sha256((salt + pw).encode()).hexdigest()

def check_pw(pw, salt, h):
    return hashlib.sha256((salt + pw).encode()).hexdigest() == h

def auth_user():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "): return None
    token = h[7:].strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT username FROM tokens WHERE token=%s", (token,))
    r = cur.fetchone()
    cur.close(); conn.close()
    return r[0] if r else None

@app.route("/")
def root():
    return render_template("index.html")

@app.route("/api/register", methods=["POST"])
def register():
    d = request.get_json() or {}
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    if len(username) < 3: return jsonify({"error":"Ник минимум 3 символа"}), 400
    if len(username) > 20: return jsonify({"error":"Ник максимум 20 символов"}), 400
    if " " in username: return jsonify({"error":"Пробелы запрещены"}), 400
    if not username.replace("_","").replace("-","").isalnum():
        return jsonify({"error":"Только буквы, цифры, _ и -"}), 400
    if len(password) < 3: return jsonify({"error":"Пароль минимум 3 символа"}), 400

    salt, h = hash_pw(password)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE LOWER(username)=LOWER(%s)", (username,))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error":"Ник занят"}), 400
    try:
        cur.execute(
            "INSERT INTO users (username, salt, hash, pw_plain, created, coins, per_click, cps, click_lvl, cps_lvl, level, version) "
            "VALUES (%s, %s, %s, %s, %s, 0, 1, 0, 0, 0, 1, 0) RETURNING id",
            (username, salt, h, password, time.time())
        )
        uid = cur.fetchone()[0]
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error":"Ник занят"}), 400
    finally:
        try: cur.close()
        except: pass
        try: conn.close()
        except: pass

    token = secrets.token_urlsafe(24)
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO tokens (token, username, created) VALUES (%s, %s, %s)",
                (token, username, time.time()))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok":True, "token":token, "username":username, "id":uid})

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json() or {}
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, salt, hash FROM users WHERE LOWER(username)=LOWER(%s)", (username,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error":"Аккаунт не найден"}), 400
    uid, salt, h = row
    if not check_pw(password, salt, h):
        cur.close(); conn.close()
        return jsonify({"error":"Неверный пароль"}), 400
    cur.execute("SELECT username, COALESCE(pw_plain, '') FROM users WHERE id=%s", (uid,))
    r2 = cur.fetchone()
    real_username = r2[0]
    if not r2[1]:
        cur.execute("UPDATE users SET pw_plain=%s WHERE id=%s", (password, uid))
    token = secrets.token_urlsafe(24)
    cur.execute("INSERT INTO tokens (token, username, created) VALUES (%s, %s, %s)",
                (token, real_username, time.time()))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok":True, "token":token, "username":real_username, "id":uid})

@app.route("/api/me")
def me():
    uname = auth_user()
    if not uname: return jsonify({"ok":False}), 401
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, username FROM users WHERE username=%s", (uname,))
    u = cur.fetchone()
    cur.close(); conn.close()
    if not u: return jsonify({"ok":False}), 401
    return jsonify({"ok":True, "username":u["username"], "id":u["id"]})

@app.route("/api/state")
def state():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    import time as _t
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE users SET last_seen=%s WHERE username=%s", (_t.time(), uname))
    conn.commit()
    cur.close(); conn.close()
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT coins, per_click, cps, click_lvl, cps_lvl, level, version, COALESCE(infinite, FALSE) AS infinite FROM users WHERE username=%s", (uname,))
    u = cur.fetchone()
    cur.close(); conn.close()
    if not u: return jsonify({"error":"not_logged_in"}), 401
    return jsonify({
        "coins": int(u["coins"]),
        "perClick": int(u["per_click"]),
        "cps": int(u["cps"]),
        "clickLvl": int(u["click_lvl"]),
        "cpsLvl": int(u["cps_lvl"]),
        "level": int(u["level"]),
        "version": int(u["version"]),
        "infinite": bool(u["infinite"])
    })

@app.route("/api/save", methods=["POST"])
def save_state():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    inc = request.get_json() or {}
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT version FROM users WHERE username=%s", (uname,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return jsonify({"error":"not_logged_in"}), 401
    if int(inc.get("version",0)) < int(u["version"]):
        cur.close(); conn.close()
        return jsonify({"conflict": True})
    cur.execute(
        "UPDATE users SET coins=%s, per_click=%s, cps=%s, click_lvl=%s, cps_lvl=%s, level=%s, version=%s WHERE username=%s",
        (int(inc.get("coins",0)), int(inc.get("perClick",1)), int(inc.get("cps",0)),
         int(inc.get("clickLvl",0)), int(inc.get("cpsLvl",0)), int(inc.get("level",1)),
         int(u["version"])+1, uname)
    )
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok":True, "version": int(u["version"])+1})

@app.route("/api/logout", methods=["POST"])
def logout():
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM tokens WHERE token=%s", (h[7:].strip(),))
        conn.commit()
        cur.close(); conn.close()
    return jsonify({"ok":True})


@app.route("/api/top")
def top():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT username, coins, level, cps FROM users ORDER BY coins DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{"username":r[0], "coins":int(r[1]), "level":int(r[2]), "cps":int(r[3])} for r in rows])

@app.route("/api/user/<username>")
def user_profile(username):
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, username, coins, per_click, cps, click_lvl, cps_lvl, level, created FROM users WHERE LOWER(username)=LOWER(%s)", (username,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r: return jsonify({"error":"not_found"}), 404
    return jsonify({
        "id": r[0], "username": r[1],
        "coins": int(r[2]), "perClick": int(r[3]),
        "cps": int(r[4]), "clickLvl": int(r[5]),
        "cpsLvl": int(r[6]), "level": int(r[7]),
        "created": r[8]
    })


@app.route("/api/unions")
def list_unions():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    search = (request.args.get("search") or "").strip()
    conn = get_db(); cur = conn.cursor()
    if search:
        cur.execute("""
            SELECT u.id, u.name, u.tag, u.color, u.description, u.founder, u.created,
                   (SELECT COUNT(*) FROM union_members m WHERE m.union_id=u.id) AS cnt,
                   COALESCE(u.closed, FALSE), COALESCE(u.treasury, 0)
            FROM unions u WHERE LOWER(u.name) LIKE LOWER(%s) OR LOWER(u.tag) LIKE LOWER(%s)
            ORDER BY cnt DESC, u.id ASC LIMIT 50
        """, (f"%{search}%", f"%{search}%"))
    else:
        cur.execute("""
            SELECT u.id, u.name, u.tag, u.color, u.description, u.founder, u.created,
                   (SELECT COUNT(*) FROM union_members m WHERE m.union_id=u.id) AS cnt,
                   COALESCE(u.closed, FALSE), COALESCE(u.treasury, 0)
            FROM unions u ORDER BY cnt DESC, u.id ASC LIMIT 50
        """)
    rows = cur.fetchall()
    cur.execute("SELECT union_id FROM union_members WHERE username=%s", (uname,))
    my = cur.fetchone()
    my_union = my[0] if my else None
    cur.close(); conn.close()
    return jsonify({
        "my_union_id": my_union,
        "unions": [{
            "id":r[0], "name":r[1], "tag":r[2], "color":r[3],
            "description":r[4], "founder":r[5], "created":r[6], "members":int(r[7]),
            "closed": bool(r[8]), "treasury": int(r[9])
        } for r in rows]
    })

@app.route("/api/unions", methods=["POST"])
def create_union():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    name = (d.get("name") or "").strip()
    tag  = (d.get("tag") or "").strip().upper()
    desc = (d.get("description") or "").strip()[:120]
    closed = bool(d.get("closed", False))
    if len(name) < 3: return jsonify({"error":"Название минимум 3 символа"}), 400
    if len(name) > 40: return jsonify({"error":"Название максимум 40"}), 400
    if len(tag) < 2 or len(tag) > 4: return jsonify({"error":"Тег 2-4 символа"}), 400
    if not tag.isalpha(): return jsonify({"error":"Тег только из букв"}), 400

    import random as _r, time as _t
    color = _r.choice(["#e17076","#7bc862","#e5ca77","#65aadd","#a695e7","#ee7aae","#6ec9cb","#faa774"])
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT union_id FROM union_members WHERE username=%s", (uname,))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error":"Ты уже в союзе"}), 400
    try:
        cur.execute(
            "INSERT INTO unions (name, tag, color, description, founder, created, closed, treasury) VALUES (%s,%s,%s,%s,%s,%s,%s,0) RETURNING id",
            (name, tag, color, desc or "Союз, основанный игроками", uname, _t.time(), closed)
        )
        uid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO union_members (username, union_id, joined, role) VALUES (%s,%s,%s,'founder')",
            (uname, uid, _t.time())
        )
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback(); cur.close(); conn.close()
        return jsonify({"error":"Такое название уже занято"}), 400
    finally:
        try: cur.close()
        except: pass
        try: conn.close()
        except: pass
    return jsonify({"ok":True, "id":uid})

@app.route("/api/unions/join", methods=["POST"])
def join_union():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    union_id = d.get("id")
    if not union_id: return jsonify({"error":"Не указан союз"}), 400
    import time as _t
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT union_id FROM union_members WHERE username=%s", (uname,))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error":"Сначала выйди из текущего союза"}), 400
    cur.execute("SELECT id, COALESCE(closed, FALSE), founder FROM unions WHERE id=%s", (union_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error":"Союз не найден"}), 404
    if row[1]:
        cur.close(); conn.close()
        return jsonify({"error":"Союз закрыт для входа"}), 403
    cur.execute(
        "INSERT INTO union_members (username, union_id, joined, role) VALUES (%s,%s,%s,'member')",
        (uname, union_id, _t.time())
    )
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/unions/leave", methods=["POST"])
def leave_union():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT union_id, role FROM union_members WHERE username=%s", (uname,))
    r = cur.fetchone()
    if not r:
        cur.close(); conn.close()
        return jsonify({"error":"Ты не в союзе"}), 400
    uid, role = r
    cur.execute("DELETE FROM union_members WHERE username=%s", (uname,))
    # если основатель вышел и никого не осталось — удаляем союз
    if role == "founder":
        cur.execute("SELECT COUNT(*) FROM union_members WHERE union_id=%s", (uid,))
        if cur.fetchone()[0] == 0:
            cur.execute("DELETE FROM unions WHERE id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/unions/<int:uid>/toggle_closed", methods=["POST"])
def union_toggle_closed(uid):
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT role FROM union_members WHERE username=%s AND union_id=%s", (uname, uid))
    r = cur.fetchone()
    if not r or r[0] != "founder":
        cur.close(); conn.close()
        return jsonify({"error":"Только основатель может менять"}), 403
    cur.execute("SELECT COALESCE(closed, FALSE) FROM unions WHERE id=%s", (uid,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error":"Союз не найден"}), 404
    new_val = not row[0]
    cur.execute("UPDATE unions SET closed=%s WHERE id=%s", (new_val, uid))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True, "closed": new_val})

@app.route("/api/unions/<int:uid>/deposit", methods=["POST"])
def union_deposit(uid):
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    amount = int(d.get("amount") or 0)
    if amount <= 0: return jsonify({"error":"Сумма должна быть > 0"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM union_members WHERE username=%s AND union_id=%s", (uname, uid))
    if not cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error":"Ты не в этом союзе"}), 403
    cur.execute("SELECT coins, COALESCE(infinite, FALSE) FROM users WHERE username=%s", (uname,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return jsonify({"error":"Юзер не найден"}), 404
    if not u[1]:
        if int(u[0]) < amount:
            cur.close(); conn.close()
            return jsonify({"error":"Не хватает монет"}), 400
        cur.execute("UPDATE users SET coins = coins - %s, version = version + 1 WHERE username=%s", (amount, uname))
    cur.execute("UPDATE unions SET treasury = COALESCE(treasury,0) + %s WHERE id=%s", (amount, uid))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True, "amount":amount})

@app.route("/api/unions/top")
def top_unions():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.tag, u.color, COALESCE(u.treasury,0) as treasury,
               (SELECT COUNT(*) FROM union_members m WHERE m.union_id=u.id) as cnt
        FROM unions u ORDER BY treasury DESC, cnt DESC LIMIT 50
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{
        "id":r[0], "name":r[1], "tag":r[2], "color":r[3],
        "treasury":int(r[4]), "members":int(r[5])
    } for r in rows])

@app.route("/api/unions/<int:uid>")
def union_info(uid):
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, name, tag, color, description, founder, created, COALESCE(closed, FALSE), COALESCE(treasury, 0) FROM unions WHERE id=%s", (uid,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return jsonify({"error":"not_found"}), 404
    cur.execute("SELECT username, joined, role FROM union_members WHERE union_id=%s ORDER BY joined ASC", (uid,))
    members = cur.fetchall()
    cur.close(); conn.close()
    # я в этом союзе?
    cur.execute("SELECT 1 FROM union_members WHERE username=%s AND union_id=%s", (uname, uid))
    in_this = bool(cur.fetchone())
    # роли
    cur.execute("SELECT role FROM union_members WHERE username=%s AND union_id=%s", (uname, uid))
    rr = cur.fetchone()
    my_role = rr[0] if rr else None
    cur.close(); conn.close()
    return jsonify({
        "id":u[0], "name":u[1], "tag":u[2], "color":u[3],
        "description":u[4], "founder":u[5], "created":u[6],
        "closed": bool(u[7]), "treasury": int(u[8]),
        "in_this": in_this, "my_role": my_role,
        "members":[{"username":m[0], "joined":m[1], "role":m[2]} for m in members]
    })


# ---------- SKINS ----------
SKINS_CATALOG = {
    "classic":  {"name": "Классика",  "price": 0,             "emoji": "🪙"},
    "silver":   {"name": "Серебро",   "price": 10000,         "emoji": "🥈"},
    "gold":     {"name": "Золото",    "price": 100000,        "emoji": "🥇"},
    "emerald":  {"name": "Изумруд",   "price": 500000,        "emoji": "💚"},
    "ruby":     {"name": "Рубин",     "price": 2000000,       "emoji": "🔴"},
    "diamond":  {"name": "Алмаз",     "price": 10000000,      "emoji": "💎"},
    "neon":     {"name": "Неон",      "price": 50000000,      "emoji": "🟣"},
    "fire":     {"name": "Огонь",     "price": 200000000,     "emoji": "🔥"},
    "ice":      {"name": "Лёд",       "price": 500000000,     "emoji": "❄️"},
    "cosmic":   {"name": "Космос",    "price": 5000000000,    "emoji": "🌌"},
    "rainbow":  {"name": "Радуга",    "price": 100000000000,  "emoji": "🌈"},
}

@app.route("/api/skins")
def skins_list():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COALESCE(skin, 'classic') FROM users WHERE username=%s", (uname,))
    row = cur.fetchone()
    my_skin = row[0] if row else "classic"
    cur.execute("SELECT skin_id FROM user_skins WHERE username=%s", (uname,))
    owned = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    if "classic" not in owned: owned.insert(0, "classic")
    return jsonify({"my_skin": my_skin, "owned": owned, "catalog": SKINS_CATALOG})

@app.route("/api/skins/buy", methods=["POST"])
def skins_buy():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    skin_id = d.get("skin_id")
    if skin_id not in SKINS_CATALOG: return jsonify({"error":"Неизвестный скин"}), 400
    price = SKINS_CATALOG[skin_id]["price"]
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM user_skins WHERE username=%s AND skin_id=%s", (uname, skin_id))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error":"Уже куплен"}), 400
    cur.execute("SELECT coins, COALESCE(infinite, FALSE) FROM users WHERE username=%s", (uname,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return jsonify({"error":"Юзер не найден"}), 404
    if not u[1] and int(u[0]) < price:
        cur.close(); conn.close()
        return jsonify({"error":"Не хватает монет"}), 400
    if not u[1]:
        cur.execute("UPDATE users SET coins = coins - %s, version = version + 1 WHERE username=%s", (price, uname))
    import time as _t
    cur.execute("INSERT INTO user_skins (username, skin_id, bought) VALUES (%s,%s,%s)", (uname, skin_id, _t.time()))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/skins/select", methods=["POST"])
def skins_select():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    skin_id = d.get("skin_id")
    if skin_id not in SKINS_CATALOG: return jsonify({"error":"Неизвестный"}), 400
    if skin_id != "classic":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT 1 FROM user_skins WHERE username=%s AND skin_id=%s", (uname, skin_id))
        if not cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error":"Сначала купи"}), 400
        cur.close(); conn.close()
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE users SET skin=%s, version=version+1 WHERE username=%s", (skin_id, uname))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True})

# ---------- CASINO ----------
@app.route("/api/casino/flip", methods=["POST"])
def casino_flip():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    bet = int(d.get("bet") or 0)
    choice = (d.get("choice") or "").lower()
    if bet <= 0: return jsonify({"error":"Ставка должна быть > 0"}), 400
    if choice not in ("heads","tails"): return jsonify({"error":"Выбери: heads или tails"}), 400
    import random as _r
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT coins, COALESCE(infinite, FALSE) FROM users WHERE username=%s", (uname,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return jsonify({"error":"Юзер не найден"}), 404
    if not u[1] and int(u[0]) < bet:
        cur.close(); conn.close()
        return jsonify({"error":"Не хватает монет"}), 400
    result = _r.choice(["heads","tails"])
    win = (result == choice)
    if u[1]:
        pass  # infinite — ничего не списываем/добавляем
    else:
        if win:
            cur.execute("UPDATE users SET coins = coins + %s, version = version + 1 WHERE username=%s", (bet, uname))
        else:
            cur.execute("UPDATE users SET coins = coins - %s, version = version + 1 WHERE username=%s", (bet, uname))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True, "result": result, "win": win, "bet": bet})

@app.route("/api/casino/dice", methods=["POST"])
def casino_dice():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    bet = int(d.get("bet") or 0)
    if bet <= 0: return jsonify({"error":"Ставка > 0"}), 400
    import random as _r
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT coins, COALESCE(infinite, FALSE) FROM users WHERE username=%s", (uname,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return jsonify({"error":"Юзер не найден"}), 404
    if not u[1] and int(u[0]) < bet:
        cur.close(); conn.close()
        return jsonify({"error":"Не хватает монет"}), 400
    roll = _r.randint(1, 6)
    # 6 = x3, 5 = x2, 4 = x1 (вернули), 1-3 = проигрыш
    mult = {6: 3, 5: 2, 4: 1}.get(roll, 0)
    if u[1]:
        pass
    else:
        delta = bet * mult - bet
        cur.execute("UPDATE users SET coins = coins + %s, version = version + 1 WHERE username=%s", (delta, uname))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True, "roll": roll, "mult": mult, "bet": bet})

# ---------- BROADCAST ----------
@app.route("/api/broadcast")
def get_broadcast():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    import time as _t
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, text, author, created FROM broadcasts WHERE expires > %s ORDER BY id DESC LIMIT 1", (_t.time(),))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r: return jsonify({"broadcast": None})
    return jsonify({"broadcast": {"id":r[0], "text":r[1], "author":r[2], "created":r[3]}})


# ---------- KICK ----------
@app.route("/api/unions/kick", methods=["POST"])
def union_kick():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    target = (d.get("username") or "").strip()
    if not target: return jsonify({"error":"Не указан ник"}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT union_id, role FROM union_members WHERE username=%s", (uname,))
    me = cur.fetchone()
    if not me or me[1] != "founder":
        cur.close(); conn.close()
        return jsonify({"error":"Только основатель может кикать"}), 403
    my_uid = me[0]
    if target.lower() == uname.lower():
        cur.close(); conn.close()
        return jsonify({"error":"Себя нельзя"}), 400
    cur.execute("SELECT union_id FROM union_members WHERE LOWER(username)=LOWER(%s)", (target,))
    t = cur.fetchone()
    if not t or t[0] != my_uid:
        cur.close(); conn.close()
        return jsonify({"error":"Игрок не в твоём союзе"}), 400
    cur.execute("DELETE FROM union_members WHERE LOWER(username)=LOWER(%s)", (target,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True})

# ---------- BANNERS ----------
BANNER_EMOJIS = ["👑","💠","🔥","⭐","💎","🚀","🌌","🌈","⚡","🏆","💰","🧠"]
BANNER_COLORS = ["#e17076","#7bc862","#e5ca77","#65aadd","#a695e7","#ee7aae","#6ec9cb","#faa774","#ff9d5c","#d4262a"]

@app.route("/api/banners/<username>")
def user_banners(username):
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT slot, emoji, color, label FROM user_banners WHERE LOWER(username)=LOWER(%s) ORDER BY slot", (username,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{"slot":r[0], "emoji":r[1], "color":r[2], "label":r[3]} for r in rows])

@app.route("/api/banners", methods=["POST"])
def set_banner():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    d = request.get_json() or {}
    slot = int(d.get("slot", 0))
    emoji = (d.get("emoji") or "").strip()
    color = (d.get("color") or "").strip()
    label = (d.get("label") or "").strip()[:40]
    if slot < 1 or slot > 6: return jsonify({"error":"Слот 1-6"}), 400
    if emoji not in BANNER_EMOJIS: return jsonify({"error":"Недопустимый emoji"}), 400
    if color not in BANNER_COLORS: return jsonify({"error":"Недопустимый цвет"}), 400
    import time as _t
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_banners (username, slot, emoji, color, label, created)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (username, slot) DO UPDATE
        SET emoji=EXCLUDED.emoji, color=EXCLUDED.color, label=EXCLUDED.label
    """, (uname, slot, emoji, color, label, _t.time()))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/banners/<int:slot>", methods=["DELETE"])
def del_banner(slot):
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM user_banners WHERE username=%s AND slot=%s", (uname, slot))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok":True})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
