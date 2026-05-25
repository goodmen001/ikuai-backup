import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from ..config import BACKUP_DIR

logger = logging.getLogger("ikuai-backup")


class BackupManager:
    def __init__(self, app_ctx):
        self.ctx = app_ctx

    def _get_backup_path(self):
        return Path(getattr(self.ctx, "_backup_path", str(BACKUP_DIR)))

    def cleanup_old_backups(self):
        backup_path = self._get_backup_path()
        keep = getattr(self.ctx, "_keep_backup_num", 7)
        if keep <= 0:
            return
        if not backup_path.is_dir():
            return

        files = []
        for f in backup_path.iterdir():
            if f.is_file() and f.suffix.lower() == ".bak":
                try:
                    match = re.search(r'(\d{4}\d{2}\d{2}[_]?\d{2}\d{2}\d{2})', f.stem)
                    file_time = None
                    if match:
                        try:
                            file_time = datetime.strptime(match.group(1).replace('_', ''), '%Y%m%d%H%M%S').timestamp()
                        except ValueError:
                            pass
                    if file_time is None:
                        file_time = f.stat().st_mtime
                    files.append((file_time, f))
                except Exception:
                    files.append((f.stat().st_mtime, f))

        files.sort(key=lambda x: x[0], reverse=True)
        if len(files) > keep:
            for _, f in files[keep:]:
                try:
                    f.unlink()
                    logger.info(f"已删除旧备份: {f.name}")
                except Exception as e:
                    logger.error(f"删除旧备份 {f.name} 失败: {e}")

    def upload_to_webdav(self, local_file_path: str, filename: str) -> Tuple[bool, Optional[str]]:
        if not getattr(self.ctx, "_enable_webdav", False) or not getattr(self.ctx, "_webdav_url", ""):
            return False, "WebDAV未启用"
        try:
            from ..webdav.webdav_client import WebDAVClient
            client = WebDAVClient(
                url=self.ctx._webdav_url, username=self.ctx._webdav_username,
                password=self.ctx._webdav_password, path=self.ctx._webdav_path,
                skip_dir_check=True, logger=logger, plugin_name="iKuai-Backup",
            )
            success, error = client.upload(local_file_path, filename)
            client.close()
            return success, error
        except Exception as e:
            return False, f"WebDAV上传失败: {e}"

    def cleanup_webdav_backups(self):
        if not getattr(self.ctx, "_enable_webdav", False) or not getattr(self.ctx, "_webdav_url", ""):
            return
        keep = getattr(self.ctx, "_webdav_keep_backup_num", 7)
        if keep <= 0:
            return
        try:
            from ..webdav.webdav_client import WebDAVClient
            client = WebDAVClient(
                url=self.ctx._webdav_url, username=self.ctx._webdav_username,
                password=self.ctx._webdav_password, path=self.ctx._webdav_path,
                skip_dir_check=True, logger=logger, plugin_name="iKuai-Backup",
            )
            deleted, error = client.cleanup_old_files(keep_count=keep, pattern='.bak')
            if error:
                logger.error(f"WebDAV清理失败: {error}")
            else:
                logger.info(f"WebDAV清理完成，已删除 {deleted} 个旧文件")
            client.close()
        except Exception as e:
            logger.error(f"WebDAV清理异常: {e}")

    def get_available_backups(self) -> List[Dict[str, Any]]:
        backups = []
        backup_path = self._get_backup_path()

        if getattr(self.ctx, "_enable_local_backup", True) and backup_path.is_dir():
            for f in backup_path.iterdir():
                if f.is_file() and f.suffix.lower() == ".bak":
                    try:
                        stat = f.stat()
                        backups.append({
                            "filename": f.name, "path": str(f),
                            "size_mb": stat.st_size / (1024 * 1024),
                            "time_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "time": stat.st_mtime, "source": "本地备份",
                        })
                    except Exception:
                        pass

        if getattr(self.ctx, "_enable_webdav", False) and getattr(self.ctx, "_webdav_url", ""):
            try:
                from ..webdav.webdav_client import WebDAVClient
                client = WebDAVClient(
                    url=self.ctx._webdav_url, username=self.ctx._webdav_username,
                    password=self.ctx._webdav_password, path=self.ctx._webdav_path,
                    skip_dir_check=True, logger=logger, plugin_name="iKuai-Backup",
                )
                files, error = client.list_files('.bak')
                if not error:
                    for fi in files:
                        ft = fi.get("time")
                        backups.append({
                            "filename": fi["filename"], "path": fi.get("href", ""),
                            "size_mb": fi.get("size_mb", 0),
                            "time_str": datetime.fromtimestamp(ft).strftime("%Y-%m-%d %H:%M:%S") if ft else "未知",
                            "time": ft or 0, "source": "WebDAV备份",
                        })
                client.close()
            except Exception:
                pass

        backups.sort(key=lambda x: x.get("time", 0), reverse=True)
        return backups

    def download_from_webdav(self, filename: str, local_path: str) -> Tuple[bool, Optional[str]]:
        if not getattr(self.ctx, "_enable_webdav", False) or not getattr(self.ctx, "_webdav_url", ""):
            return False, "WebDAV未启用"
        try:
            from ..webdav.webdav_client import WebDAVClient
            client = WebDAVClient(
                url=self.ctx._webdav_url, username=self.ctx._webdav_username,
                password=self.ctx._webdav_password, path=self.ctx._webdav_path,
                skip_dir_check=True, logger=logger, plugin_name="iKuai-Backup",
            )
            success, error = client.download(filename, local_path)
            client.close()
            return success, error
        except Exception as e:
            return False, f"WebDAV下载失败: {e}"
