import logging
from typing import List, Dict, Any

logger = logging.getLogger("ikuai-backup")


class HistoryHandler:
    def __init__(self, app_ctx):
        self.ctx = app_ctx
        self.max_backup = 100
        self.max_restore = 50

    def load_backup_history(self) -> List[Dict[str, Any]]:
        data = self.ctx.get_data("backup_history")
        return data if isinstance(data, list) else []

    def save_backup_history_entry(self, entry: Dict[str, Any]):
        try:
            history = self.load_backup_history()
            history.insert(0, entry)
            if len(history) > self.max_backup:
                history = history[:self.max_backup]
            self.ctx.save_data("backup_history", history)
        except Exception as e:
            logger.error(f"保存备份历史失败: {e}")

    def load_restore_history(self) -> List[Dict[str, Any]]:
        data = self.ctx.get_data("restore_history")
        return data if isinstance(data, list) else []

    def save_restore_history_entry(self, entry: Dict[str, Any]):
        try:
            history = self.load_restore_history()
            history.insert(0, entry)
            if len(history) > self.max_restore:
                history = history[:self.max_restore]
            self.ctx.save_data("restore_history", history)
        except Exception as e:
            logger.error(f"保存恢复历史失败: {e}")

    def clear_all_history(self):
        self.ctx.save_data("backup_history", [])
        self.ctx.save_data("restore_history", [])
        logger.info("已清理所有历史记录")
