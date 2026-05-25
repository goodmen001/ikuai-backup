import os
import time
import threading
import tempfile
import logging
from pathlib import Path

from ..config import BACKUP_DIR, DATA_DIR
from ..ikuai.client import IkuaiClient
from ..ip_group.manager import IPGroupManager

logger = logging.getLogger("ikuai-backup")


class APIHandler:
    def __init__(self, ctx):
        self.ctx = ctx

    # ── Config ──
    def get_config(self):
        return self.ctx.get_config()

    def save_config(self, data: dict):
        cfg = self.ctx.get_config()
        cfg.update(data)
        self.ctx.save_config(cfg)
        for k, v in data.items():
            setattr(self.ctx, f"_{k}", v)
        self.ctx.scheduler_manager.setup_scheduler()
        return {"success": True, "message": "配置已保存"}

    # ── Status ──
    def get_status(self):
        next_run = None
        if self.ctx._scheduler:
            job = self.ctx._scheduler.get_job("ikuai_backup_cron")
            if job and job.next_run_time:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "enabled": self.ctx._enabled if hasattr(self.ctx, "_enabled") else False,
            "backup_activity": self.ctx._backup_activity,
            "restore_activity": self.ctx._restore_activity,
            "ip_group_activity": self.ctx._ip_group_activity,
            "cron": getattr(self.ctx, "_cron", "0 3 * * *"),
            "next_run_time": next_run,
        }

    # ── Dashboard ──
    def get_dashboard_data(self):
        bh = self.ctx.history_handler.load_backup_history()
        rh = self.ctx.history_handler.load_restore_history()
        ab = self.ctx.backup_manager.get_available_backups()
        return {
            "backup_stats": {
                "total": len(bh),
                "successful": sum(1 for x in bh if x.get("success")),
                "failed": sum(1 for x in bh if not x.get("success")),
            },
            "restore_stats": {
                "total": len(rh),
                "successful": sum(1 for x in rh if x.get("success")),
                "failed": sum(1 for x in rh if not x.get("success")),
            },
            "available_backups": {
                "local": sum(1 for x in ab if x["source"] == "本地备份"),
                "webdav": sum(1 for x in ab if x["source"] == "WebDAV备份"),
                "total": len(ab),
            },
            "status": {
                "backup_activity": self.ctx._backup_activity,
                "restore_activity": self.ctx._restore_activity,
                "running": self.ctx._running,
            },
        }

    # ── History ──
    def get_backup_history(self):
        return self.ctx.history_handler.load_backup_history() or []

    def get_restore_history(self):
        return self.ctx.history_handler.load_restore_history() or []

    def clear_history(self):
        self.ctx.history_handler.clear_all_history()
        return {"success": True, "message": "历史已清理"}

    # ── Backup actions ──
    def run_backup(self):
        threading.Thread(target=self.ctx.backup_executor.run_backup_job, daemon=True).start()
        return {"success": True, "message": "备份任务已启动"}

    def get_available_backups(self):
        return self.ctx.backup_manager.get_available_backups() or []

    def delete_backup(self, data: dict):
        fn = data.get("filename", "")
        src = data.get("source", "本地备份")
        if not fn:
            return {"success": False, "message": "缺少文件名"}
        if src == "本地备份":
            bp = Path(getattr(self.ctx, "_backup_path", str(BACKUP_DIR)))
            fp = bp / fn
            if not fp.is_file() or not str(fp.resolve()).startswith(str(bp.resolve())):
                return {"success": False, "message": "文件不存在"}
            os.remove(fp)
            return {"success": True, "message": f"已删除: {fn}"}
        elif src == "WebDAV备份":
            from ..webdav.webdav_client import WebDAVClient
            client = WebDAVClient(
                url=self.ctx._webdav_url, username=self.ctx._webdav_username,
                password=self.ctx._webdav_password, path=self.ctx._webdav_path,
                skip_dir_check=True, logger=logger, plugin_name="iKuai-Backup",
            )
            ok, err = client.delete_file(fn)
            client.close()
            if ok:
                return {"success": True, "message": f"已删除WebDAV: {fn}"}
            return {"success": False, "message": f"删除失败: {err}"}
        return {"success": False, "message": "不支持的来源"}

    # ── Restore ──
    def restore_backup(self, data: dict):
        fn = data.get("filename", "")
        src = data.get("source", "本地备份")
        if not fn:
            return {"success": False, "message": "缺少文件名"}
        threading.Thread(
            target=self.ctx.restore_executor.run_restore_job,
            args=(fn, src), daemon=True
        ).start()
        return {"success": True, "message": f"已启动恢复: {fn}"}

    # ── iKuai Status ──
    def _get_ikuai_client(self):
        host = getattr(self.ctx, "_ikuai_url", "")
        user = getattr(self.ctx, "_ikuai_username", "")
        pwd = getattr(self.ctx, "_ikuai_password", "")
        if not host or not user or not pwd:
            return None
        client = IkuaiClient(host, user, pwd, plugin_name="iKuai-API")
        if not client.login():
            return None
        return client

    def get_system_info(self):
        client = self._get_ikuai_client()
        if not client:
            return {"success": False, "message": "iKuai连接失败"}
        try:
            info = client.get_system_info()
            return info or {"success": False, "message": "获取系统信息失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_monitor_info(self):
        client = self._get_ikuai_client()
        if not client:
            return {"success": False, "message": "iKuai连接失败"}
        try:
            info = client.get_monitor_info()
            return info or {"success": False, "message": "获取监控信息失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_interface_info(self):
        client = self._get_ikuai_client()
        if not client:
            return {"success": False, "message": "iKuai连接失败"}
        try:
            info = client.get_interface_info()
            return info or {"success": False, "message": "获取接口信息失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── IP Group ──
    def sync_ip_groups(self, data: dict):
        host = getattr(self.ctx, "_ikuai_url", "")
        user = getattr(self.ctx, "_ikuai_username", "")
        pwd = getattr(self.ctx, "_ikuai_password", "")
        if not host or not user or not pwd:
            return {"success": False, "message": "iKuai配置不完整"}
        try:
            ip_manager = IPGroupManager(host, user, pwd)
            province = data.get("province") or getattr(self.ctx, "_ip_group_province", "")
            city = data.get("city") or getattr(self.ctx, "_ip_group_city", "")
            isp = data.get("isp") or getattr(self.ctx, "_ip_group_isp", "")
            prefix = data.get("prefix") or getattr(self.ctx, "_ip_group_prefix", "")
            pool = data.get("address_pool", getattr(self.ctx, "_ip_group_address_pool", False))
            success, msg = ip_manager.sync_ip_groups_from_22tool(province, city, isp, prefix, pool)
            return {"success": success, "message": msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_ip_blocks_info(self, data: dict):
        host = getattr(self.ctx, "_ikuai_url", "")
        user = getattr(self.ctx, "_ikuai_username", "")
        pwd = getattr(self.ctx, "_ikuai_password", "")
        try:
            ip_manager = IPGroupManager(host, user, pwd)
            province = data.get("province", "")
            city = data.get("city", "")
            isp = data.get("isp", "")
            blocks = ip_manager.get_ip_blocks_from_22tool(province, city, isp)
            return {"success": True, "data": blocks, "count": len(blocks)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_available_options(self):
        host = getattr(self.ctx, "_ikuai_url", "")
        user = getattr(self.ctx, "_ikuai_username", "")
        pwd = getattr(self.ctx, "_ikuai_password", "")
        try:
            ip_manager = IPGroupManager(host, user, pwd)
            provinces = ip_manager.get_available_provinces()
            isps = ip_manager.get_available_isps()
            return {"success": True, "provinces": provinces, "isps": isps}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_cities_by_province(self, province: str):
        host = getattr(self.ctx, "_ikuai_url", "")
        user = getattr(self.ctx, "_ikuai_username", "")
        pwd = getattr(self.ctx, "_ikuai_password", "")
        try:
            ip_manager = IPGroupManager(host, user, pwd)
            cities = ip_manager.get_available_cities(province)
            return {"success": True, "cities": cities}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def test_ip_group(self):
        host = getattr(self.ctx, "_ikuai_url", "")
        user = getattr(self.ctx, "_ikuai_username", "")
        pwd = getattr(self.ctx, "_ikuai_password", "")
        if not host or not user or not pwd:
            return {"code": 1, "msg": "配置不完整"}
        try:
            ip_manager = IPGroupManager(host, user, pwd)
            success, error = ip_manager.test_create_simple_ip_group()
            if success:
                return {"code": 0, "msg": "测试成功"}
            return {"code": 1, "msg": f"测试失败: {error}"}
        except Exception as e:
            return {"code": 1, "msg": str(e)}

    # ── Misc ──
    def stop_all_tasks(self):
        stopped = []
        for lock_name in ("_lock", "_restore_lock", "_global_task_lock"):
            lock = getattr(self.ctx, lock_name, None)
            if lock and lock.locked():
                try:
                    lock.release()
                    stopped.append(lock_name)
                except RuntimeError:
                    pass
        self.ctx._running = False
        self.ctx._backup_activity = "空闲"
        self.ctx._restore_activity = "空闲"
        msg = f"已停止: {', '.join(stopped)}" if stopped else "无运行中的任务"
        return {"success": True, "message": msg}

    def download_backup(self, filename: str, source: str = "本地备份"):
        if source == "本地备份":
            bp = Path(getattr(self.ctx, "_backup_path", str(BACKUP_DIR)))
            fp = bp / filename
            if fp.is_file() and str(fp.resolve()).startswith(str(bp.resolve())):
                return str(fp)
            return None
        elif source == "WebDAV备份":
            tmp = Path(tempfile.gettempdir()) / "ikuai_backup_download"
            tmp.mkdir(parents=True, exist_ok=True)
            dest = str(tmp / filename)
            ok, err = self.ctx.backup_manager.download_from_webdav(filename, dest)
            if ok:
                return dest
            return None
        return None

    def test_notification(self):
        from ..notification.notifications import CHANNEL_DESCRIPTIONS
        channels = getattr(self.ctx, "_notify_channels", {}) or {}
        results = {}
        for ch_name, ch_conf in channels.items():
            if not ch_conf.get("enabled"):
                results[ch_name] = {"sent": False, "error": "未启用"}
                continue
            desc = CHANNEL_DESCRIPTIONS.get(ch_name, {})
            label = desc.get("label", ch_name)
            title = f"{label} 测试通知"
            text = f"这是一条来自 iKuai Backup 的测试通知\n如果你收到这条消息，说明通知配置正确 ✅\n\n⏱️ {__import__('time').time()}"
            try:
                method = getattr(self.ctx.notification_handler, f"_send_{ch_name}", None)
                if method:
                    method(title, text, ch_conf)
                    results[ch_name] = {"sent": True, "error": None}
                else:
                    results[ch_name] = {"sent": False, "error": "未知渠道"}
            except Exception as e:
                results[ch_name] = {"sent": False, "error": str(e)}
        return {"success": True, "results": results}

    def get_token(self):
        return {"api_token": os.environ.get("IKUAI_API_TOKEN", "ikuai-backup-token")}
