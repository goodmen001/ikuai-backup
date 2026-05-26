import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.request import Request, urlopen
from urllib.parse import quote

logger = logging.getLogger("ikuai-backup")

CHANNEL_DESCRIPTIONS = {
    "webhook": {
        "label": "Webhook",
        "desc": "通用Webhook通知，POST JSON到指定URL，适用于飞书/钉钉/企业微信自定义机器人",
        "fields": {
            "url": {"label": "Webhook URL", "type": "text", "placeholder": "https://oapi.dingtalk.com/robot/send?access_token=..."},
        },
    },
    "bark": {
        "label": "Bark (iOS推送)",
        "desc": "Bark iOS推送通知，需在iOS设备安装Bark App获取推送Key",
        "fields": {
            "key": {"label": "Bark Key", "type": "text", "placeholder": "xxxxxxxxxxxx"},
            "server": {"label": "推送服务器", "type": "text", "placeholder": "https://api.day.app"},
        },
    },
    "pushdeer": {
        "label": "PushDeer",
        "desc": "PushDeer推送，支持iOS/Android/桌面端，https://pushdeer.com 获取PushKey",
        "fields": {
            "key": {"label": "PushKey", "type": "text", "placeholder": "PDxxx..."},
            "server": {"label": "API服务器", "type": "text", "placeholder": "https://api2.pushdeer.com"},
        },
    },
    "serverchan": {
        "label": "Server酱 (微信推送)",
        "desc": "Server酱·Turbo版，推送通知到微信，https://sct.ftqq.com 获取SendKey",
        "fields": {
            "key": {"label": "SendKey", "type": "text", "placeholder": "SCTxxx..."},
        },
    },
    "gotify": {
        "label": "Gotify (自托管推送)",
        "desc": "Gotify自托管消息推送，支持Android/Web端，需自建服务端",
        "fields": {
            "server": {"label": "服务器地址", "type": "text", "placeholder": "http://192.168.9.105:8080"},
            "token": {"label": "App Token", "type": "text", "placeholder": "Axxxxxxxxx.xxxx"},
        },
    },
}


def get_default_notify_channels() -> dict:
    return {
        "webhook": {"enabled": False, "url": ""},
        "bark": {"enabled": False, "key": "", "server": "https://api.day.app"},
        "pushdeer": {"enabled": False, "key": "", "server": "https://api2.pushdeer.com"},
        "serverchan": {"enabled": False, "key": ""},
        "gotify": {"enabled": False, "server": "", "token": ""},
    }


class NotificationHandler:
    def __init__(self, app_ctx):
        self.ctx = app_ctx

    def _should_notify(self) -> bool:
        return getattr(self.ctx, "_notify", False)

    def _get_channels(self) -> dict:
        return getattr(self.ctx, "_notify_channels", {}) or get_default_notify_channels()

    def _send_all(self, title: str, text: str):
        channels = self._get_channels()
        for ch_name, ch_conf in channels.items():
            if not ch_conf.get("enabled"):
                continue
            method = getattr(self, f"_send_{ch_name}", None)
            if method:
                try:
                    method(title, text, ch_conf)
                except Exception as e:
                    logger.warning(f"通知渠道 [{ch_name}] 发送失败: {e}")

    @staticmethod
    def _send_webhook(title: str, text: str, conf: dict):
        url = conf.get("url", "").strip()
        if not url:
            return
        payload = json.dumps({"title": title, "text": text}).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        urlopen(req, timeout=10)

    @staticmethod
    def _send_bark(title: str, text: str, conf: dict):
        key = conf.get("key", "").strip()
        server = conf.get("server", "https://api.day.app").strip().rstrip("/")
        if not key:
            return
        url = f"{server}/{quote(key)}/{quote(title)}/{quote(text)}"
        req = Request(url)
        urlopen(req, timeout=10)

    @staticmethod
    def _send_pushdeer(title: str, text: str, conf: dict):
        key = conf.get("key", "").strip()
        server = conf.get("server", "https://api2.pushdeer.com").strip().rstrip("/")
        if not key:
            return
        payload = json.dumps({"pushkey": key, "text": title, "desp": text, "type": "markdown"}).encode("utf-8")
        req = Request(f"{server}/message/push", data=payload, headers={"Content-Type": "application/json"})
        urlopen(req, timeout=10)

    @staticmethod
    def _send_serverchan(title: str, text: str, conf: dict):
        key = conf.get("key", "").strip()
        if not key:
            return
        data = f"title={quote(title)}&desp={quote(text)}".encode("utf-8")
        req = Request(f"https://sctapi.ftqq.com/{key}.send", data=data)
        urlopen(req, timeout=10)

    @staticmethod
    def _send_gotify(title: str, text: str, conf: dict):
        server = conf.get("server", "").strip().rstrip("/")
        token = conf.get("token", "").strip()
        if not server or not token:
            return
        payload = json.dumps({"title": title, "message": text, "priority": 5}).encode("utf-8")
        req = Request(f"{server}/message?token={token}", data=payload,
                      headers={"Content-Type": "application/json"})
        urlopen(req, timeout=10)

    def send_backup_notification(
        self, success: bool, message: str = "",
        filename: Optional[str] = None, backup_details: Optional[Dict[str, Any]] = None, **kwargs,
    ):
        if not self._should_notify():
            return
        status = "成功" if success else "失败"
        title = f"iKuai备份 {status}"
        text = ""
        if success:
            text += "✅ iKuai备份任务已成功完成\n"
        else:
            text += "❌ iKuai备份任务执行失败\n"
        host = getattr(self.ctx, "_ikuai_url", "-")
        text += f"主机: {host}\n"
        if filename:
            text += f"文件: {filename}\n"
        if message:
            text += f"详情: {message}\n"
        text += f"\n⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        logger.info(f"通知: {title}\n{text}")
        self._send_all(title, text)

    def send_restore_notification(
        self, success: bool, message: str = "",
        filename: str = "", **kwargs,
    ):
        if not self._should_notify():
            return
        status = "成功" if success else "失败"
        title = f"iKuai恢复 {status}"
        text = ""
        if success:
            text += "✅ iKuai恢复任务已成功完成\n"
        else:
            text += "❌ iKuai恢复任务执行失败\n"
        host = getattr(self.ctx, "_ikuai_url", "-")
        text += f"主机: {host}\n"
        if filename:
            text += f"文件: {filename}\n"
        if message:
            text += f"详情: {message}\n"
        text += f"\n⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        logger.info(f"通知: {title}\n{text}")
        self._send_all(title, text)
