# -*- coding: utf-8 -*-
"""测试公共设施：被测skill路径解析、sys.path注入、联网探测、临时目录"""
import os
import shutil
import socket
import sys
import tempfile

DEFAULT_SKILL = r'C:\Users\Administrator\.config\opencode\skills\视觉硬件选型'
SKILL_DIR = os.environ.get('VISION_SKILL_DIR', DEFAULT_SKILL)
TOOLS_DIR = os.path.join(SKILL_DIR, 'tools')
WORKSPACE = os.environ.get('VISION_WORKSPACE', r'E:\Agent工作空间\视觉方案')

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

_checked_online = None


def online(host='www.hikrobotics.com', port=443, timeout=2.5):
    """官网可达性探测（结果缓存；在线用例用它做 skipUnless）"""
    global _checked_online
    if _checked_online is None:
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            _checked_online = True
        except OSError:
            _checked_online = False
    return _checked_online


def temp_dir(prefix='vt_'):
    """独立临时目录（用例自清理）"""
    return tempfile.mkdtemp(prefix=prefix)


def rmtree(path):
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def copy_real_db(dst_path):
    """真实库的临时副本（写库类用例的数据源，绝不指向真实库）"""
    src = os.path.join(SKILL_DIR, 'config', 'hardware_database.json')
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copy2(src, dst_path)
    return dst_path


def workspace_ready():
    """工作区（config+模板）是否就绪——端到端重用例的前置条件"""
    cfg = os.path.join(WORKSPACE, 'project_config.json')
    if not os.path.isfile(cfg):
        return False
    for f in os.listdir(WORKSPACE):
        if f.lower().endswith('.pptx'):
            return True
    return False
