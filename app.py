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
    try:
        cur.execute(
            "INSERT INTO users (username, salt, hash, created, coins, per_click, cps, click_lvl, cps_lvl, level, version) "
            "VALUES (%s, %s, %s, %s, 0, 1, 0, 0, 0, 1, 0) RETURNING id",
            (username, salt, h, time.time())
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
    cur.execute("SELECT username FROM users WHERE id=%s", (uid,))
    real_username = cur.fetchone()[0]
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
    conn = get_db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT coins, per_click, cps, click_lvl, cps_lvl, level, version FROM users WHERE username=%s", (uname,))
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
        "version": int(u["version"])
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
                   (SELECT COUNT(*) FROM union_members m WHERE m.union_id=u.id) AS cnt
            FROM unions u WHERE LOWER(u.name) LIKE LOWER(%s) OR LOWER(u.tag) LIKE LOWER(%s)
            ORDER BY cnt DESC, u.id ASC LIMIT 50
        """, (f"%{search}%", f"%{search}%"))
    else:
        cur.execute("""
            SELECT u.id, u.name, u.tag, u.color, u.description, u.founder, u.created,
                   (SELECT COUNT(*) FROM union_members m WHERE m.union_id=u.id) AS cnt
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
            "description":r[4], "founder":r[5], "created":r[6], "members":int(r[7])
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
            "INSERT INTO unions (name, tag, color, description, founder, created) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (name, tag, color, desc or "Союз, основанный игроками", uname, _t.time())
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
    cur.execute("SELECT id FROM unions WHERE id=%s", (union_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error":"Союз не найден"}), 404
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

@app.route("/api/unions/<int:uid>")
def union_info(uid):
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, name, tag, color, description, founder, created FROM unions WHERE id=%s", (uid,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return jsonify({"error":"not_found"}), 404
    cur.execute("SELECT username, joined, role FROM union_members WHERE union_id=%s ORDER BY joined ASC", (uid,))
    members = cur.fetchall()
    cur.close(); conn.close()
    return jsonify({
        "id":u[0], "name":u[1], "tag":u[2], "color":u[3],
        "description":u[4], "founder":u[5], "created":u[6],
        "members":[{"username":m[0], "joined":m[1], "role":m[2]} for m in members]
    })

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
