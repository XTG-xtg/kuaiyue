#!/usr/bin/env python3
"""
快阅 — ComfyUI图片浏览筛选工具
"""
import os, json, shutil, io, zipfile
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, send_from_directory, request,
                   jsonify, session, send_file)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(32).hex()
app.permanent_session_lifetime = timedelta(days=30)

IMAGE_DIR = ""
TRASH_DIR = ""
USERS_FILE = ""
GROUPS_FILE = ""
LOGIN_LOG_FILE = ""

# ── 工具 ──────────────────────────────────────────────────

def load_json(path, default=None):
    if not Path(path).exists():
        if default is not None:
            save_json(path, default)
        return default or {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── 用户管理 ──────────────────────────────────────────────

def load_users():
    default = {"admin": {"password": generate_password_hash("admin123"), "role": "admin"}}
    return load_json(USERS_FILE, default)

def save_users(users):
    save_json(USERS_FILE, users)

def get_current_user():
    return session.get("user")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            return jsonify({"error": "未登录"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "未登录"}), 401
        if user.get("role") != "admin":
            return jsonify({"error": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated

def log_login(username):
    """记录登录历史"""
    logs = load_json(LOGIN_LOG_FILE, [])
    logs.insert(0, {
        "user": username,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ip": request.remote_addr or "unknown"
    })
    # 只保留最近100条
    save_json(LOGIN_LOG_FILE, logs[:100])

# ── 图片管理 ──────────────────────────────────────────────

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

def get_images(directory, prefix=None):
    images = []
    for f in Path(directory).iterdir():
        if f.suffix.lower() in EXTS:
            if prefix and not f.name.startswith(prefix):
                continue
            stat = f.stat()
            images.append({
                "name": f.name,
                "size": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "mtime": stat.st_mtime,
                "mtime_str": datetime.fromtimestamp(stat.st_mtime).strftime("%m-%d %H:%M"),
            })
    images.sort(key=lambda x: x["mtime"], reverse=True)
    return images

def get_prefixes(directory):
    prefixes = set()
    for f in Path(directory).iterdir():
        if f.suffix.lower() in EXTS:
            name = f.stem
            for i, c in enumerate(name):
                if c.isdigit():
                    prefix = name[:i]
                    if prefix and len(prefix) > 2:
                        prefixes.add(prefix)
                    break
    return sorted(prefixes)

# ── 路由 ──────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

# ── 认证 ──────────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get("username", "")
    password = data.get("password", "")
    users = load_users()

    if username not in users or not check_password_hash(users[username]["password"], password):
        return jsonify({"error": "用户名或密码错误"}), 401

    session.permanent = True
    session["user"] = {"name": username, "role": users[username]["role"]}
    log_login(username)
    return jsonify({"ok": True, "user": session["user"]})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("user", None)
    return jsonify({"ok": True})

@app.route("/api/me")
def api_me():
    user = get_current_user()
    if not user:
        return jsonify({"logged_in": False}), 401
    return jsonify({"logged_in": True, "user": user})

# ── 用户管理（管理员） ────────────────────────────────────

@app.route("/api/users")
@admin_required
def api_list_users():
    users = load_users()
    return jsonify({"users": [{"name": n, "role": u["role"]} for n, u in users.items()]})

@app.route("/api/users", methods=["POST"])
@admin_required
def api_create_user():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    users = load_users()
    if username in users:
        return jsonify({"error": "用户已存在"}), 400
    users[username] = {"password": generate_password_hash(password), "role": role}
    save_users(users)
    return jsonify({"ok": True})

@app.route("/api/users/<username>", methods=["DELETE"])
@admin_required
def api_delete_user(username):
    users = load_users()
    if username not in users:
        return jsonify({"error": "用户不存在"}), 404
    if username == "admin":
        return jsonify({"error": "不能删除默认管理员"}), 400
    del users[username]
    save_users(users)
    return jsonify({"ok": True})

@app.route("/api/users/<username>/password", methods=["PUT"])
@login_required
def api_change_password(username):
    user = get_current_user()
    if user["name"] != username and user["role"] != "admin":
        return jsonify({"error": "无权操作"}), 403
    data = request.json
    new_pw = data.get("password", "").strip()
    if not new_pw:
        return jsonify({"error": "密码不能为空"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "用户不存在"}), 404
    users[username]["password"] = generate_password_hash(new_pw)
    save_users(users)
    return jsonify({"ok": True})

@app.route("/api/login-log")
@login_required
def api_login_log():
    user = get_current_user()
    logs = load_json(LOGIN_LOG_FILE, [])
    if user["role"] != "admin":
        logs = [l for l in logs if l["user"] == user["name"]]
    return jsonify({"logs": logs[:20]})

# ── 图片接口 ──────────────────────────────────────────────

@app.route("/api/images")
@login_required
def api_images():
    prefix = request.args.get("prefix", "")
    images = get_images(IMAGE_DIR, prefix if prefix else None)
    prefixes = get_prefixes(IMAGE_DIR)
    return jsonify({"images": images, "prefixes": prefixes})

@app.route("/api/delete", methods=["POST"])
@admin_required
def api_delete():
    data = request.json
    files = data.get("files", [])
    if not files:
        return jsonify({"error": "没有选择文件"}), 400
    os.makedirs(TRASH_DIR, exist_ok=True)
    deleted, errors = [], []
    for fname in files:
        src = Path(IMAGE_DIR) / fname
        dst = Path(TRASH_DIR) / fname
        if src.exists():
            try:
                shutil.move(str(src), str(dst))
                deleted.append(fname)
            except Exception as e:
                errors.append(f"{fname}: {e}")
        else:
            errors.append(f"{fname}: 文件不存在")
    return jsonify({"deleted": deleted, "errors": errors})

@app.route("/api/restore", methods=["POST"])
@admin_required
def api_restore():
    data = request.json
    files = data.get("files", [])
    restored = []
    for fname in files:
        src = Path(TRASH_DIR) / fname
        dst = Path(IMAGE_DIR) / fname
        if src.exists():
            shutil.move(str(src), str(dst))
            restored.append(fname)
    return jsonify({"restored": restored})

# ── 分组 ──────────────────────────────────────────────────

@app.route("/api/groups")
@login_required
def api_groups():
    groups_meta = load_json(GROUPS_FILE, {})
    exts = EXTS
    result = []
    for prefix, meta in groups_meta.items():
        files = sorted([f.name for f in Path(IMAGE_DIR).iterdir()
                        if f.suffix.lower() in exts and f.name.startswith(prefix)])
        if not files:
            continue
        result.append({
            "prefix": prefix,
            "name": meta.get("name", prefix),
            "source": meta.get("source", ""),
            "description": meta.get("description", ""),
            "preview": files[0],
            "count": len(files),
        })
    result.sort(key=lambda x: x["count"], reverse=True)
    return jsonify({"groups": result})

@app.route("/api/group/<prefix>")
@login_required
def api_group_detail(prefix):
    groups_meta = load_json(GROUPS_FILE, {})
    meta = groups_meta.get(prefix, {"name": prefix, "source": "", "description": ""})
    images = get_images(IMAGE_DIR, prefix)
    return jsonify({"prefix": prefix, "meta": meta, "images": images})

# ── 下载 ──────────────────────────────────────────────────

@app.route("/images/<path:filename>")
@login_required
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route("/api/download/<path:filename>")
@login_required
def api_download(filename):
    filepath = Path(IMAGE_DIR) / filename
    if not filepath.exists():
        return jsonify({"error": "文件不存在"}), 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)

@app.route("/api/download-batch", methods=["POST"])
@login_required
def api_download_batch():
    data = request.json
    files = data.get("files", [])
    if not files:
        return jsonify({"error": "没有选择文件"}), 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in files:
            fpath = Path(IMAGE_DIR) / fname
            if fpath.exists():
                zf.write(str(fpath), fname)
    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(buf, mimetype="application/zip",
                     as_attachment=True,
                     download_name=f"快阅_{ts}_{len(files)}张.zip")

# ── 启动 ──────────────────────────────────────────────────

def main():
    global IMAGE_DIR, TRASH_DIR, USERS_FILE, GROUPS_FILE, LOGIN_LOG_FILE

    import argparse
    parser = argparse.ArgumentParser(description="快阅 — 图片浏览筛选工具")
    parser.add_argument("--dir", default="/home/xtg/.hermes/cache/generated")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    IMAGE_DIR = os.path.abspath(args.dir)
    TRASH_DIR = os.path.join(IMAGE_DIR, ".trash")
    USERS_FILE = os.path.join(base, "users.json")
    GROUPS_FILE = os.path.join(base, "groups.json")
    LOGIN_LOG_FILE = os.path.join(base, "login_log.json")

    if not Path(IMAGE_DIR).exists():
        print(f"✗ 目录不存在: {IMAGE_DIR}")
        return

    load_users()

    count = sum(1 for f in Path(IMAGE_DIR).iterdir() if f.suffix.lower() in EXTS)
    print(f"快阅")
    print(f"  目录: {IMAGE_DIR}")
    print(f"  图片: {count}张")
    print(f"  地址: http://localhost:{args.port}")

    app.run(host=args.host, port=args.port, debug=False)

if __name__ == "__main__":
    main()
