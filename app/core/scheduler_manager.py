import logging
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("ikuai-backup")

TZ = "Asia/Shanghai"


class SchedulerManager:
    def __init__(self, app_ctx):
        self.ctx = app_ctx

    def setup_scheduler(self):
        if self.ctx._scheduler:
            try:
                self.ctx._scheduler.remove_all_jobs()
                if self.ctx._scheduler.running:
                    self.ctx._scheduler.shutdown(wait=True)
            except Exception as e:
                logger.error(f"停止调度器出错: {e}")
            self.ctx._scheduler = None

        enabled = getattr(self.ctx, "_enabled", False)
        onlyonce = getattr(self.ctx, "_onlyonce", False)
        cron = getattr(self.ctx, "_cron", "0 3 * * *")

        if enabled or onlyonce:
            self.ctx._scheduler = BackgroundScheduler(timezone=TZ)

            if onlyonce:
                job_name = "ikuai_backup_onlyonce"
                logger.info("服务启动，立即运行一次备份")
                self.ctx._scheduler.add_job(
                    func=self.ctx.backup_executor.run_backup_job,
                    trigger="date",
                    run_date=datetime.now(pytz.timezone(TZ)) + timedelta(seconds=3),
                    name=job_name,
                    id=job_name,
                )
                self.ctx._onlyonce = False
                cfg = self.ctx.get_config()
                cfg["onlyonce"] = False
                self.ctx.save_config(cfg)

            ip_group_sync_now = getattr(self.ctx, "_ip_group_sync_now", False)
            if ip_group_sync_now:
                job_name = "ikuai_ipgroup_sync_onlyonce"
                self.ctx._scheduler.add_job(
                    func=self._run_ip_group_sync,
                    trigger="date",
                    run_date=datetime.now(pytz.timezone(TZ)) + timedelta(seconds=3),
                    name=job_name,
                    id=job_name,
                )
                self.ctx._ip_group_sync_now = False
                cfg = self.ctx.get_config()
                cfg["ip_group_sync_now"] = False
                self.ctx.save_config(cfg)

            if cron and cron.count(" ") == 4 and enabled:
                job_name = "ikuai_backup_cron"
                try:
                    trigger = CronTrigger.from_crontab(cron, timezone=TZ)
                    self.ctx._scheduler.add_job(
                        func=self.ctx.backup_executor.run_backup_job,
                        trigger=trigger,
                        name=job_name,
                        id=job_name,
                    )
                    logger.info(f"已注册定时备份: {cron}")
                except Exception as e:
                    logger.error(f"cron表达式错误: {cron}, {e}")

            if not self.ctx._scheduler.running:
                self.ctx._scheduler.start()

    def _run_ip_group_sync(self):
        self.ctx._ip_group_activity = "正在同步"
        try:
            from ..ip_group.manager import IPGroupManager
            host = getattr(self.ctx, "_ikuai_url", "")
            user = getattr(self.ctx, "_ikuai_username", "")
            pwd = getattr(self.ctx, "_ikuai_password", "")
            if not host or not user or not pwd:
                logger.error("配置不完整，无法同步IP分组")
                return
            ip_manager = IPGroupManager(host, user, pwd)
            province = getattr(self.ctx, "_ip_group_province", "")
            city = getattr(self.ctx, "_ip_group_city", "")
            isp = getattr(self.ctx, "_ip_group_isp", "")
            prefix = getattr(self.ctx, "_ip_group_prefix", "")
            pool = getattr(self.ctx, "_ip_group_address_pool", False)
            success, msg = ip_manager.sync_ip_groups_from_22tool(province, city, isp, prefix, pool)
            if success:
                logger.info(f"IP分组同步成功: {msg}")
            else:
                logger.error(f"IP分组同步失败: {msg}")
        except Exception as e:
            logger.error(f"IP分组同步异常: {e}")
        finally:
            self.ctx._ip_group_activity = "空闲"

    def stop_scheduler(self):
        try:
            if self.ctx._scheduler:
                self.ctx._scheduler.remove_all_jobs()
                if self.ctx._scheduler.running:
                    self.ctx._scheduler.shutdown(wait=True)
                self.ctx._scheduler = None
        except Exception as e:
            logger.error(f"停止调度器出错: {e}")
