"""Download Stat"""
import asyncio
import time
import os
import json
from enum import Enum
from datetime import datetime
from pyrogram import Client
from module.app import TaskNode

class DownloadState(Enum):
    """Download state"""
    Downloading = 1
    StopDownload = 2

# 全局状态变量
_download_state: DownloadState = DownloadState.Downloading

# 持久化历史记录文件路径
HISTORY_FILE = "history.json"
# 内存中的历史记录缓存
_DOWNLOAD_HISTORY = {}

def load_history():
    """从文件加载历史记录"""
    global _DOWNLOAD_HISTORY
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                _DOWNLOAD_HISTORY = json.load(f)
        except Exception:
            _DOWNLOAD_HISTORY = {}

def save_history():
    """保存历史记录到文件"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(_DOWNLOAD_HISTORY, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Save history failed: {e}")

# 初始化时加载
load_history()

def get_download_result() -> dict:
    """获取所有下载记录"""
    return _DOWNLOAD_HISTORY

def get_total_download_speed() -> int:
    """计算当前总下载速度"""
    total_speed = 0
    now = time.time()
    for key, item in _DOWNLOAD_HISTORY.items():
        if item.get('status') == 'Downloading':
            # 如果超过10秒没有更新进度，认为速度为0
            if now - item.get('last_update_time', 0) > 10:
                continue
            total_speed += item.get('download_speed', 0)
    return total_speed

def get_download_state() -> DownloadState:
    """get download state"""
    return _download_state

def set_download_state(state: DownloadState):
    """set download state"""
    global _download_state
    _download_state = state

def update_download_stat(chat_id, message_id, **kwargs):
    """通用状态更新函数"""
    key = f"{chat_id}_{message_id}"

    if key not in _DOWNLOAD_HISTORY:
        _DOWNLOAD_HISTORY[key] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "status": "Unknown",
            "file_name": "",
            "file_path": "",
            "total_size": 0,
            "down_byte": 0,
            "download_speed": 0,
            "receive_time": 0,
            "start_time": 0,
            "finish_time": 0,
            "chat_title": str(chat_id),
            "last_update_time": time.time()
        }

    _DOWNLOAD_HISTORY[key].update(kwargs)
    _DOWNLOAD_HISTORY[key]['last_update_time'] = time.time()

    # 每次状态变化（非进度更新）或每隔一定时间保存一次，这里简化为关键状态变更时保存
    # 如果是纯进度更新（包含down_byte），暂不每次都写盘以减少IO
    if 'down_byte' not in kwargs or kwargs.get('status') in ['Success', 'Failed']:
        save_history()

async def update_download_status(
    down_byte: int,
    total_size: int,
    message_id: int,
    file_name: str,
    start_time: float,
    node: TaskNode,
    client: Client,
):
    """Pyrogram 下载回调"""
    cur_time = time.time()

    if node.is_stop_transmission:
        client.stop_transmission()

    while get_download_state() == DownloadState.StopDownload:
        if node.is_stop_transmission:
            client.stop_transmission()
        await asyncio.sleep(1)

    key = f"{node.chat_id}_{message_id}"

    # 计算速度
    speed = 0
    if cur_time - start_time > 0:
        speed = int(down_byte / (cur_time - start_time))

    # 更新内存和文件
    # 注意：这里频繁调用，所以不要在这里调用 save_history
    if key not in _DOWNLOAD_HISTORY:
        # 如果是第一次回调，可能 update_stat 还没建立完整记录（理论上 add_task 已建立）
        update_download_stat(
            node.chat_id, message_id,
            status="Downloading",
            start_time=start_time
        )

    _DOWNLOAD_HISTORY[key].update({
        "down_byte": down_byte,
        "total_size": total_size,
        "download_speed": speed,
        "file_name": file_name, # 这里通常是临时文件名
        "status": "Downloading",
        "last_update_time": cur_time
    })