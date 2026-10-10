from flask import Flask, request, jsonify, render_template, g
import json, os, secrets, hashlib, time, threading

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)
USERS = os.path.join(DATA, "users.json")
TOKENS = os.path.join(DATA, "tokens.json")

app = Flask(__name__)
LOCK = threading.Lock()

DEFAULTS = {"coins":0, "perClick":1, "cps":0, "clickLvl":0, "cpsLvl":0, "level":1}

def _load(path, default):
    if not os.path.exists(path): return default
    try: return json.load(open(path))
    except: return default

def _save(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)

def load_users():  return _load(USERS, {})
def save_users(u): _save(USERS, u)
def load_tokens(): return _load(TOKENS, {})
def save_tokens(t): _save(TOKENS, t)

def hash_pw(pw, salt=None):
    if salt is None: salt = secrets.token_hex(16)
    return salt, hashlib.sha256((salt + pw).encode()).hexdigest()

def check_pw(pw, salt, h):
    return hashlib.sha256((salt + pw).encode()).hexdigest() == h

def auth_user():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "): return None
    token = h[7:].strip()
    tokens = load_tokens()
    uname = tokens.get(token)
    if not uname: return None
    users = load_users()
    return uname if uname in users else None

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

    with LOCK:
        users = load_users()
        key = username.lower()
        for u in users.values():
            if u["username"].lower() == key:
                return jsonify({"error":"Ник занят"}), 400
        salt, h = hash_pw(password)
        uid = max([u.get("id",0) for u in users.values()] + [0]) + 1
        users[key] = {
            "id": uid,
            "username": username,
            "salt": salt,
            "hash": h,
            "created": time.time(),
            **DEFAULTS
        }
        save_users(users)
        token = secrets.token_urlsafe(24)
        tokens = load_tokens()
        tokens[token] = key
        save_tokens(tokens)
        return jsonify({"ok":True, "token":token, "username":username, "id":uid})

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json() or {}
    username = (d.get("username") or "").strip().lower()
    password = d.get("password") or ""
    users = load_users()
    u = users.get(username)
    if not u: return jsonify({"error":"Аккаунт не найден"}), 400
    if not check_pw(password, u["salt"], u["hash"]):
        return jsonify({"error":"Неверный пароль"}), 400
    token = secrets.token_urlsafe(24)
    tokens = load_tokens()
    tokens[token] = username
    save_tokens(tokens)
    return jsonify({"ok":True, "token":token, "username":u["username"], "id":u["id"]})

@app.route("/api/me")
def me():
    uname = auth_user()
    if not uname: return jsonify({"ok":False}), 401
    u = load_users().get(uname, {})
    return jsonify({"ok":True, "username":u.get("username"), "id":u.get("id")})

@app.route("/api/state")
def state():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    users = load_users()
    u = users[uname]
    return jsonify({
        "coins": u.get("coins",0),
        "perClick": u.get("perClick",1),
        "cps": u.get("cps",0),
        "clickLvl": u.get("clickLvl",0),
        "cpsLvl": u.get("cpsLvl",0),
        "level": u.get("level",1),
        "version": u.get("version",0)
    })

@app.route("/api/save", methods=["POST"])
def save_state():
    uname = auth_user()
    if not uname: return jsonify({"error":"not_logged_in"}), 401
    inc = request.get_json() or {}
    with LOCK:
        users = load_users()
        u = users[uname]
        if inc.get("version",0) < u.get("version",0):
            return jsonify({"conflict":True})
        for k in ["coins","perClick","cps","clickLvl","cpsLvl","level"]:
            if k in inc: u[k] = inc[k]
        u["version"] = u.get("version",0) + 1
        users[uname] = u
        save_users(users)
        return jsonify({"ok":True, "version":u["version"]})

@app.route("/api/logout", methods=["POST"])
def logout():
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        tokens = load_tokens()
        tokens.pop(h[7:].strip(), None)
        save_tokens(tokens)
    return jsonify({"ok":True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
