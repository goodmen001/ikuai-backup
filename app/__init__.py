import os
import secrets
import threading
from pathlib import Path
from typing import Optional

from flask import Flask, session, redirect, request
from flask_cors import CORS

from .config import load_config, save_config, DATA_DIR, BACKUP_DIR
from .logger import logger


class AppContext:
    """Central application context holding all managers and state."""

    def __init__(self):
        self._scheduler = None
        self._lock: Optional[threading.Lock] = None
        self._restore_lock: Optional[threading.Lock] = None
        self._global_task_lock: Optional[threading.Lock] = None
        self._running: bool = False
        self._backup_activity: str = "空闲"
        self._restore_activity: str = "空闲"
        self._ip_group_activity: str = "空闲"

        self._history_handler = None
        self._notification_handler = None
        self._backup_manager = None
        self._backup_executor = None
        self._restore_executor = None
        self._scheduler_manager = None
        self._config_manager = None

        self._last_config_hash: Optional[str] = None
        self._stopped: bool = False

    @staticmethod
    def get_config() -> dict:
        return load_config()

    @staticmethod
    def save_config(config: dict):
        save_config(config)

    @staticmethod
    def get_data_path() -> str:
        return str(DATA_DIR)

    @staticmethod
    def get_data(key: str):
        import json
        fpath = DATA_DIR / f"{key}.json"
        if fpath.exists():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @staticmethod
    def save_data(key: str, data):
        import json
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fpath = DATA_DIR / f"{key}.json"
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存数据 {key} 失败: {e}")

    @property
    def history_handler(self):
        if self._history_handler is None:
            from .core.history import HistoryHandler
            self._history_handler = HistoryHandler(self)
        return self._history_handler

    @property
    def notification_handler(self):
        if self._notification_handler is None:
            from .notification import NotificationHandler
            self._notification_handler = NotificationHandler(self)
        return self._notification_handler

    @property
    def backup_manager(self):
        if self._backup_manager is None:
            from .backup.backup_manager import BackupManager
            self._backup_manager = BackupManager(self)
        return self._backup_manager

    @property
    def backup_executor(self):
        if self._backup_executor is None:
            from .backup.backup_executor import BackupExecutor
            self._backup_executor = BackupExecutor(self)
        return self._backup_executor

    @property
    def restore_executor(self):
        if self._restore_executor is None:
            from .restore.restore_executor import RestoreExecutor
            self._restore_executor = RestoreExecutor(self)
        return self._restore_executor

    @property
    def scheduler_manager(self):
        if self._scheduler_manager is None:
            from .core.scheduler_manager import SchedulerManager
            self._scheduler_manager = SchedulerManager(self)
        return self._scheduler_manager

    @property
    def config_manager(self):
        if self._config_manager is None:
            from .core.config_manager import ConfigManager
            self._config_manager = ConfigManager(self)
        return self._config_manager

    def init_app_config(self):
        cfg = self.get_config()
        for k, v in cfg.items():
            setattr(self, f"_{k}", v)

    def ensure_backup_dirs(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)


ctx = AppContext()


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    CORS(app, supports_credentials=True)

    # Session config
    app.secret_key = os.environ.get("IKUAI_BACKUP_SECRET_KEY", secrets.token_hex(32))
    app.config["SESSION_PERMANENT"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    ctx.init_app_config()
    ctx.ensure_backup_dirs()

    ctx._lock = threading.Lock()
    ctx._restore_lock = threading.Lock()
    ctx._global_task_lock = threading.Lock()

    ctx.scheduler_manager.setup_scheduler()

    from .api.routes import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from .login_page import LOGIN_PAGE

    @app.route("/")
    def index():
        if not session.get("authenticated"):
            return LOGIN_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"}
        return app.send_static_file("index.html")

    return app
