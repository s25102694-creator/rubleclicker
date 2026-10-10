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

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
