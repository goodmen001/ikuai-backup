import os
import json
import time
import threading
import logging
from pathlib import Path
from typing import Tuple, Optional
from urllib.parse import urljoin

from ..config import BACKUP_DIR

logger = logging.getLogger("ikuai-backup")


class BackupExecutor:
    def __init__(self, app_ctx):
        self.ctx = app_ctx

    def run_backup_job(self):
        if not self.ctx._lock:
            self.ctx._lock = threading.Lock()
        if not self.ctx._global_task_lock:
            self.ctx._global_task_lock = threading.Lock()

        if self.ctx._restore_lock and self.ctx._restore_lock.locked():
            logger.info("恢复任务正在执行，备份跳过")
            return
        if not self.ctx._global_task_lock.acquire(blocking=False):
            logger.debug("其他任务执行中，备份跳过")
            return
        if not self.ctx._lock.acquire(blocking=False):
            logger.debug("已有备份执行中，跳过")
            self.ctx._global_task_lock.release()
            return

        entry = {"timestamp": time.time(), "success": False, "filename": None, "message": "开始"}
        self.ctx._backup_activity = "开始"

        try:
            self.ctx._running = True
            logger.info("开始iKuai备份任务...")

            host = getattr(self.ctx, "_ikuai_url", "")
            user = getattr(self.ctx, "_ikuai_username", "")
            pwd = getattr(self.ctx, "_ikuai_password", "")
            if not host or not user or not pwd:
                err = "iKuai配置不完整"
                logger.error(err)
                self.ctx.notification_handler.send_backup_notification(success=False, message=err)
                entry["message"] = err
                self.ctx.history_handler.save_backup_history_entry(entry)
                return

            bpath = getattr(self.ctx, "_backup_path", str(BACKUP_DIR))
            Path(bpath).mkdir(parents=True, exist_ok=True)

            for i in range(getattr(self.ctx, "_retry_count", 0) + 1):
                ok, err_msg, fname = self._perform_once(host, user, pwd)
                if ok:
                    self.ctx.notification_handler.send_backup_notification(
                        success=True, message="备份成功", filename=fname
                    )
                    entry.update({"success": True, "filename": fname, "message": "成功"})
                    self.ctx.history_handler.save_backup_history_entry(entry)
                    return
                else:
                    logger.warning(f"第{i+1}次备份失败: {err_msg}")
                    if i < getattr(self.ctx, "_retry_count", 0):
                        time.sleep(getattr(self.ctx, "_retry_interval", 60))

            entry["message"] = f"备份失败: {err_msg}"
            self.ctx.history_handler.save_backup_history_entry(entry)
            self.ctx.notification_handler.send_backup_notification(success=False, message=entry["message"])

        except Exception as e:
            logger.error(f"备份主流程异常: {e}")
            entry["message"] = f"异常: {e}"
            self.ctx.history_handler.save_backup_history_entry(entry)
            self.ctx.notification_handler.send_backup_notification(success=False, message=entry["message"])
        finally:
            self.ctx._running = False
            self.ctx._backup_activity = "空闲"
            for lock in (self.ctx._lock, self.ctx._global_task_lock):
                if lock and lock.locked():
                    try:
                        lock.release()
                    except RuntimeError:
                        pass

    def _perform_once(self, host: str, username: str, password: str) -> Tuple[bool, Optional[str], Optional[str]]:
        from ..ikuai.client import IkuaiClient

        client = IkuaiClient(host, username, password, plugin_name="iKuai-Backup")

        if not client.login():
            return False, "登录爱快路由失败", None

        create_success, create_msg = client.create_backup()
        if not create_success:
            return False, f"创建备份失败: {create_msg}", None

        logger.info("成功触发创建备份，等待2秒让备份生成...")
        time.sleep(2)

        backup_list = client.get_backup_list()
        if backup_list is None:
            return False, "获取备份文件列表失败", None
        if not backup_list:
            return False, "路由器上没有找到备份文件", None

        def get_date(x):
            return x.get("date") or x.get("backup_time") or ""

        sorted_backups = sorted(backup_list, key=get_date, reverse=True)
        latest = sorted_backups[0] if sorted_backups else None
        router_filename = latest.get("filename") or latest.get("name") if latest else None
        if not router_filename:
            return False, "无法获取最新备份的文件名", None

        base_name = os.path.splitext(router_filename)[0]
        local_filename = base_name + ".bak"
        local_filepath = Path(getattr(self.ctx, "_backup_path", str(BACKUP_DIR))) / local_filename

        # Send EXPORT request
        self._send_export_request(client.session, local_filename)

        # Local backup
        if getattr(self.ctx, "_enable_local_backup", True):
            success, msg = client.download_backup(router_filename, str(local_filepath))
            if not success:
                return False, f"下载备份失败: {msg}", None
            self.ctx.backup_manager.cleanup_old_backups()

        # WebDAV upload
        webdav_ok = False
        if getattr(self.ctx, "_enable_webdav", False):
            webdav_ok = self._upload_to_webdav(client, router_filename, local_filename, str(local_filepath))

        # 备份已下载到本地，删除路由器上的备份文件
        self._delete_backup_after_success(client, router_filename)

        return True, None, local_filename

    def _send_export_request(self, session, filename: str) -> bool:
        export_payload = {"func_name": "backup", "action": "EXPORT", "param": {"srcfile": filename}}
        export_url = urljoin(getattr(self.ctx, "_ikuai_url", ""), "/Action/call")
        try:
            session.post(export_url, data=json.dumps(export_payload),
                        headers={'Content-Type': 'application/json'}, timeout=10)
            return True
        except Exception as e:
            logger.error(f"EXPORT请求失败: {e}")
            return False

    def _upload_to_webdav(self, client, router_filename: str, local_filename: str, local_filepath: str) -> bool:
        try:
            webdav_success, webdav_msg = self.ctx.backup_manager.upload_to_webdav(local_filepath, local_filename)
            if webdav_success:
                logger.info("WebDAV备份成功")
                self.ctx.backup_manager.cleanup_webdav_backups()
            else:
                logger.error(f"WebDAV上传失败: {webdav_msg}")
            return webdav_success
        except Exception as e:
            logger.error(f"WebDAV上传异常: {e}")
            return False

    def _delete_backup_after_success(self, client, filename: str):
        logger.info(f"备份成功，删除路由器上的备份文件: {filename}")
        success, msg = client.delete_backup(filename)
        if success:
            logger.info("成功删除路由器上的备份文件")
        else:
            logger.warning(f"删除路由器备份文件失败: {msg}")
