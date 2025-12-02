"""web ui for media download"""

import logging
import os
import threading
from datetime import datetime

from flask import Flask, jsonify, render_template, request
from flask_login import LoginManager, UserMixin, login_required, login_user

import utils
from module.app import Application
from module.download_stat import (
    DownloadState,
    get_download_result,
    get_download_state,
    get_total_download_speed,
    set_download_state,
)
from utils.crypto import AesBase64
from utils.format import format_byte

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

_flask_app = Flask(__name__)

_flask_app.secret_key = "tdl"
_login_manager = LoginManager()
_login_manager.login_view = "login"
_login_manager.init_app(_flask_app)
web_login_users: dict = {}
deAesCrypt = AesBase64("1234123412ABCDEF", "ABCDEF1234123412")


class User(UserMixin):
    """Web Login User"""

    def __init__(self):
        self.sid = "root"

    @property
    def id(self):
        """ID"""
        return self.sid


@_login_manager.user_loader
def load_user(_):
    """
    Load a user object from the user ID.

    Returns:
        User: The user object.
    """
    return User()


def get_flask_app() -> Flask:
    """get flask app instance"""
    return _flask_app


def run_web_server(app: Application):
    """
    Runs a web server using the Flask framework.
    """

    get_flask_app().run(
        app.web_host, app.web_port, debug=app.debug_web, use_reloader=False
    )


# pylint: disable = W0603
def init_web(app: Application):
    """
    Set the value of the users variable.

    Args:
        users: The list of users to set.

    Returns:
        None.
    """
    global web_login_users
    if app.web_login_secret:
        web_login_users = {"root": app.web_login_secret}
    else:
        _flask_app.config["LOGIN_DISABLED"] = True
    if app.debug_web:
        threading.Thread(target=run_web_server, args=(app,)).start()
    else:
        threading.Thread(
            target=get_flask_app().run, daemon=True, args=(app.web_host, app.web_port)
        ).start()


@_flask_app.route("/login", methods=["GET", "POST"])
def login():
    """
    Function to handle the login route.
    """
    if request.method == "POST":
        username = "root"
        web_login_form = {}
        for key, value in request.form.items():
            if value:
                value = deAesCrypt.decrypt(value)
            web_login_form[key] = value

        if not web_login_form.get("password"):
            return jsonify({"code": "0"})

        password = web_login_form["password"]
        if username in web_login_users and web_login_users[username] == password:
            user = User()
            login_user(user)
            return jsonify({"code": "1"})

        return jsonify({"code": "0"})

    return render_template("login.html")


@_flask_app.route("/")
@login_required
def index():
    """Index html"""
    return render_template(
        "index.html",
        download_state=(
            "pause" if get_download_state() is DownloadState.Downloading else "continue"
        ),
    )


@_flask_app.route("/get_download_status")
@login_required
def get_download_speed():
    """Get download speed"""
    return (
        '{ "download_speed" : "'
        + format_byte(get_total_download_speed())
        + '/s" , "upload_speed" : "0.00 B/s" } '
    )


@_flask_app.route("/set_download_state", methods=["POST"])
@login_required
def web_set_download_state():
    """Set download state"""
    state = request.args.get("state")

    if state == "continue" and get_download_state() is DownloadState.StopDownload:
        set_download_state(DownloadState.Downloading)
        return "pause"

    if state == "pause" and get_download_state() is DownloadState.Downloading:
        set_download_state(DownloadState.StopDownload)
        return "continue"

    return state


@_flask_app.route("/get_app_version")
def get_app_version():
    """Get telegram_media_downloader version"""
    return utils.__version__


def format_ts(ts):
    """格式化时间戳"""
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


@_flask_app.route("/get_download_list")
@login_required
def get_download_list():
    """get download list with full history"""
    # 获取新版历史记录 (字典格式)
    raw_data = get_download_result()

    json_list = []
    # 遍历所有记录
    for key, item in raw_data.items():
        # 深拷贝以避免修改原数据
        value = item.copy()

        # 实时检测文件状态
        status = value.get('status', 'Unknown')
        file_path = value.get('file_path', '')

        if status == 'Success' and file_path:
            if not os.path.exists(file_path):
                status = 'File Missing'

        # 计算进度
        progress = 0.0
        if value.get('total_size', 0) > 0:
            progress = (value.get('down_byte', 0) / value.get('total_size')) * 100
        elif status == 'Success':
            progress = 100.0

        json_list.append({
            "chat": value.get('chat_title', str(value.get('chat_id'))),
            "id": str(value.get('message_id')),
            "filename": os.path.basename(value.get('file_name')) if value.get('file_name') else "Unknown",
            "total_size": format_byte(value.get('total_size', 0)),
            "download_progress": f"{progress:.1f}",
            "download_speed": f"{format_byte(value.get('download_speed', 0))}/s",
            "save_path": file_path,
            "status": status,
            "receive_time": format_ts(value.get('receive_time')),
            "start_time": format_ts(value.get('start_time')),
            "finish_time": format_ts(value.get('finish_time'))
        })

    # 按接收时间倒序排列 (最新的在前)
    json_list.sort(key=lambda x: x['receive_time'], reverse=True)

    return jsonify(json_list)