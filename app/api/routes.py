from flask import Blueprint, request, jsonify, send_file, abort

from ..auth import login_required, check_auth, do_login, do_logout, do_change_password
from .handlers import APIHandler
from .. import ctx

api_bp = Blueprint("api", __name__)
h = APIHandler(ctx)


# ── Auth ──
@api_bp.route("/check_auth", methods=["GET"])
def check_auth_route():
    return jsonify(check_auth())


@api_bp.route("/login", methods=["POST"])
def login():
    return jsonify(do_login(request.json or {}))


@api_bp.route("/logout", methods=["POST"])
def logout():
    return jsonify(do_logout())


@api_bp.route("/change_password", methods=["POST"])
@login_required
def change_password():
    return jsonify(do_change_password(request.json or {}))
@api_bp.route("/config", methods=["GET"])
@login_required
def get_config():
    return jsonify(h.get_config())


@api_bp.route("/config", methods=["POST"])
@login_required
def save_config():
    return jsonify(h.save_config(request.json or {}))


# ── Status ──
@api_bp.route("/status", methods=["GET"])
@login_required
def get_status():
    return jsonify(h.get_status())


# ── Dashboard ──
@api_bp.route("/dashboard_data", methods=["GET"])
@login_required
def dashboard_data():
    return jsonify(h.get_dashboard_data())


# ── History ──
@api_bp.route("/backup_history", methods=["GET"])
@login_required
def backup_history():
    return jsonify(h.get_backup_history())


@api_bp.route("/restore_history", methods=["GET"])
@login_required
def restore_history():
    return jsonify(h.get_restore_history())


@api_bp.route("/clear_history", methods=["POST"])
@login_required
def clear_history():
    return jsonify(h.clear_history())


# ── Backup ──
@api_bp.route("/run_backup", methods=["POST"])
@login_required
def run_backup():
    return jsonify(h.run_backup())


@api_bp.route("/available_backups", methods=["GET"])
@login_required
def available_backups():
    return jsonify(h.get_available_backups())


@api_bp.route("/delete_backup", methods=["POST"])
@login_required
def delete_backup():
    return jsonify(h.delete_backup(request.json or {}))


# ── Restore ──
@api_bp.route("/restore", methods=["POST"])
@login_required
def restore():
    return jsonify(h.restore_backup(request.json or {}))


# ── iKuai Status ──
@api_bp.route("/ikuai/system_info", methods=["GET"])
@login_required
def system_info():
    return jsonify(h.get_system_info())


@api_bp.route("/ikuai/monitor_info", methods=["GET"])
@login_required
def monitor_info():
    return jsonify(h.get_monitor_info())


@api_bp.route("/ikuai/interface_info", methods=["GET"])
@login_required
def interface_info():
    return jsonify(h.get_interface_info())


# ── IP Group ──
@api_bp.route("/ip_groups/sync", methods=["POST"])
@login_required
def sync_ip_groups():
    return jsonify(h.sync_ip_groups(request.json or {}))


@api_bp.route("/ip_groups/ip_blocks", methods=["POST"])
@login_required
def ip_blocks_info():
    return jsonify(h.get_ip_blocks_info(request.json or {}))


@api_bp.route("/ip_groups/options", methods=["GET"])
@login_required
def available_options():
    return jsonify(h.get_available_options())


@api_bp.route("/ip_groups/cities", methods=["GET"])
@login_required
def cities_by_province():
    province = request.args.get("province", "")
    return jsonify(h.get_cities_by_province(province))


@api_bp.route("/ip_groups/test", methods=["POST"])
@login_required
def test_ip_group():
    return jsonify(h.test_ip_group())


# ── Misc ──
@api_bp.route("/stop_all_tasks", methods=["POST"])
@login_required
def stop_all_tasks():
    return jsonify(h.stop_all_tasks())


# ── Download ──
@api_bp.route("/download_backup", methods=["GET"])
@login_required
def download_backup():
    fn = request.args.get("filename", "")
    src = request.args.get("source", "本地备份")
    if not fn:
        abort(400, description="缺少文件名")
    fp = h.download_backup(fn, src)
    if fp:
        return send_file(fp, as_attachment=True, download_name=fn, mimetype="application/octet-stream")
    abort(404, description="文件不存在")


# ── Token ──
@api_bp.route("/token", methods=["GET"])
@login_required
def token():
    return jsonify(h.get_token())


# ── Notification Test ──
@api_bp.route("/test_notification", methods=["POST"])
@login_required
def test_notification():
    return jsonify(h.test_notification())
