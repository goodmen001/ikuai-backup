import functools
import secrets

from flask import session, jsonify, request

from .config import load_config, save_config


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"success": False, "message": "未登录"}), 401
        return f(*args, **kwargs)
    return decorated


def check_auth():
    return {"authenticated": session.get("authenticated", False)}


def do_login(data: dict):
    cfg = load_config()
    username = data.get("username", "")
    password = data.get("password", "")
    if username == cfg.get("login_username", "admin") and password == cfg.get("login_password", "admin123"):
        session["authenticated"] = True
        session.permanent = True
        return {"success": True, "message": "登录成功"}
    return {"success": False, "message": "用户名或密码错误"}


def do_change_password(data: dict):
    cfg = load_config()
    old_pwd = data.get("old_password", "")
    new_pwd = data.get("new_password", "")
    if old_pwd != cfg.get("login_password", "admin123"):
        return {"success": False, "message": "当前密码错误"}
    if not new_pwd or len(new_pwd) < 4:
        return {"success": False, "message": "新密码至少4个字符"}
    cfg["login_password"] = new_pwd
    save_config(cfg)
    return {"success": True, "message": "密码修改成功"}


def do_logout():
    session.clear()
    return {"success": True, "message": "已退出"}
