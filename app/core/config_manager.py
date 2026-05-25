import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger("ikuai-backup")


class ConfigManager:
    def __init__(self, app_ctx):
        self.ctx = app_ctx

    def update_config(self, config: Optional[dict] = None):
        if config is None:
            config = {}
        for attr in dir(self.ctx):
            if attr.startswith("_") and not attr.startswith("__"):
                config[attr[1:]] = getattr(self.ctx, attr)
        self.ctx.save_config(config)

    def should_skip_reinit(self, config: Optional[dict] = None) -> bool:
        if config is None:
            return True
        special_ops = {"clear_history", "restore_now", "ip_group_sync_now"}
        if config:
            for op in special_ops:
                if config.get(op):
                    return False
        cfg_hash = hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()
        if cfg_hash == self.ctx._last_config_hash:
            return True
        self.ctx._last_config_hash = cfg_hash
        return False
