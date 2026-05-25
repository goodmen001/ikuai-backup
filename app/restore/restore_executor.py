import os
import threading
import logging
from pathlib import Path
from typing import Tuple, Optional

from ..config import DATA_DIR

logger = logging.getLogger("ikuai-backup")


class RestoreExecutor:
    def __init__(self, app_ctx):
        self.ctx = app_ctx

    def run_restore_job(self, filename: str, source: str = "本地备份"):
        if not getattr(self.ctx, "_enable_restore", False):
            logger.error("恢复功能未启用")
            return

        if not self.ctx._restore_lock:
            self.ctx._restore_lock = threading.Lock()
        if not self.ctx._global_task_lock:
            self.ctx._global_task_lock = threading.Lock()

        if not self.ctx._global_task_lock.acquire(blocking=False):
            logger.debug("其他任务正在执行，恢复跳过")
            return
        if not self.ctx._restore_lock.acquire(blocking=False):
            logger.debug("已有恢复任务执行中")
            self.ctx._global_task_lock.release()
            return

        entry = {"timestamp": __import__('time').time(), "success": False, "filename": filename, "message": "恢复任务开始"}
        self.ctx._restore_activity = "任务开始"

        try:
            logger.info(f"开始恢复任务，文件: {filename}, 来源: {source}")
            host = getattr(self.ctx, "_ikuai_url", "")
            user = getattr(self.ctx, "_ikuai_username", "")
            pwd = getattr(self.ctx, "_ikuai_password", "")
            if not host or not user or not pwd:
                err = "iKuai配置不完整"
                logger.error(err)
                self.ctx.notification_handler.send_restore_notification(success=False, message=err, filename=filename)
                entry["message"] = err
                self.ctx.history_handler.save_restore_history_entry(entry)
                return

            success, error_msg = self._perform_restore(filename, source, host, user, pwd)

            entry["success"] = success
            entry["message"] = "恢复成功" if success else f"恢复失败: {error_msg}"
            self.ctx.notification_handler.send_restore_notification(
                success=success, message=entry["message"], filename=filename
            )

        except Exception as e:
            logger.error(f"恢复主流程异常: {e}")
            entry["message"] = f"异常: {e}"
            self.ctx.notification_handler.send_restore_notification(success=False, message=entry["message"], filename=filename)
        finally:
            self.ctx._restore_activity = "空闲"
            self.ctx.history_handler.save_restore_history_entry(entry)
            for lock in (self.ctx._restore_lock, self.ctx._global_task_lock):
                if lock and lock.locked():
                    try:
                        lock.release()
                    except RuntimeError:
                        pass

    def _perform_restore(self, filename: str, source: str, host: str, username: str, password: str) -> Tuple[bool, Optional[str]]:
        from ..ikuai.client import IkuaiClient

        client = IkuaiClient(host, username, password, plugin_name="iKuai-Restore")
        if not client.login():
            return False, "登录爱快路由失败"

        backup_file_path = None
        if source == "本地备份":
            backup_path = getattr(self.ctx, "_backup_path", "")
            backup_file_path = os.path.join(backup_path, filename)
            if not os.path.exists(backup_file_path):
                return False, f"本地备份文件不存在: {backup_file_path}"
        elif source == "WebDAV备份":
            temp_dir = Path(str(DATA_DIR)) / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            backup_file_path = str(temp_dir / filename)
            self.ctx._restore_activity = "下载WebDAV中"
            ok, err = self.ctx.backup_manager.download_from_webdav(filename, backup_file_path)
            if not ok:
                return False, f"从WebDAV下载失败: {err}"
        else:
            return False, f"不支持的来源: {source}"

        try:
            with open(backup_file_path, 'rb') as f:
                backup_content = f.read()

            self.ctx._restore_activity = "正在恢复配置..."
            return client.restore_backup(filename, backup_content)
        finally:
            if source == "WebDAV备份" and backup_file_path and os.path.exists(backup_file_path):
                try:
                    os.remove(backup_file_path)
                except Exception:
                    pass
