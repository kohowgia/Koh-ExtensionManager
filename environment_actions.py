"""Explicit dependency operations in ComfyUI's interpreter; never restart.
Preview uses pip --dry-run and an in-memory single-use, 10-minute ticket.
Only allowlisted ComfyUI packages are eligible, never arbitrary pip arguments.
"""
import sys
import re
import json
import os
import tempfile
import subprocess
import importlib.metadata as metadata
import hashlib
import secrets
import time
import threading
try:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name

CORE = {'comfyui-frontend-package', 'comfyui-workflow-templates', 'comfyui-embedded-docs', 'comfy-aimdo', 'comfy-kitchen'}
_tickets = {}
_lock = threading.Lock()

def inventory():
    return sorted([(canonicalize_name(d.metadata.get('Name', '')), d.version) for d in metadata.distributions()])

def fingerprint():
    return hashlib.sha256(json.dumps(inventory()).encode()).hexdigest()

def analyze(name):
    name = canonicalize_name(name)
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,150}', name):
        raise ValueError('包名无效')
    consumers = []
    for dist in metadata.distributions():
        for raw in dist.requires or []:
            try:
                req = Requirement(raw)
                if canonicalize_name(req.name) == name:
                    # Extra-only requirements are displayed but not called active.
                    active = req.marker is None or req.marker.evaluate({'extra': ''})
                    consumers.append({'name': dist.metadata.get('Name'), 'version': dist.version, 'requirement': raw, 'active': active})
            except Exception:
                continue
    return {'name': name, 'installed': [v for n, v in inventory() if n == name], 'consumers': consumers,
            'note': '仅分析已安装包的声明；未解析插件 requirements.txt，不能据此保证修复兼容。'}

def validated_specs(items):
    if not isinstance(items, list) or not items or len(items) > 10:
        raise ValueError('请选择核心依赖包')
    specs = []
    for item in items:
        name = canonicalize_name(str(item.get('name', '')))
        version = str(item.get('version', ''))
        if name not in CORE or not re.fullmatch(r'[0-9][A-Za-z0-9.!+_-]{0,79}', version):
            raise ValueError('仅支持明确版本的 ComfyUI 核心包')
        specs.append(name + '==' + version)
    if len(set(s.split('==')[0] for s in specs)) != len(specs):
        raise ValueError('重复包名')
    return specs

def plan(items):
    specs = validated_specs(items)
    before = fingerprint()
    with tempfile.TemporaryDirectory(prefix='koh-pip-preview-') as folder:
        report = os.path.join(folder, 'report.json')
        p = subprocess.run([sys.executable, '-m', 'pip', 'install', '--dry-run', '--report', report, '--disable-pip-version-check', '--no-input', *specs], capture_output=True, text=True, timeout=180)
        if p.returncode:
            raise ValueError((p.stdout + '\n' + p.stderr)[-6000:])
        with open(report, encoding='utf-8') as f:
            raw = json.load(f)
    if before != fingerprint():
        raise ValueError('检查过程中依赖环境已变化，请重试')
    changes = [{'name': i['metadata']['name'], 'version': i['metadata']['version']} for i in raw.get('install', [])]
    # Do not silently include shared dependencies in this first repair release.
    # A dependency cascade must be handled explicitly in a future planner.
    requested = {s.split('==')[0] for s in specs}
    if any(canonicalize_name(i['name']) not in requested for i in changes):
        return {'executable': False, 'changes': changes, 'message': '方案还会改动其他依赖，当前版本仅展示，拒绝自动执行。'}
    token = secrets.token_urlsafe(24)
    if len(_tickets) > 100:
        _tickets.clear()
    _tickets[token] = {'specs': specs, 'before': before, 'expires': time.time() + 600}
    return {'token': token, 'executable': True, 'changes': changes, 'message': '仅安装所选核心包的指定版本；不会自动重启。'}

def execute(token):
    if not _lock.acquire(blocking=False):
        raise ValueError('依赖处理正在执行')
    try:
        ticket = _tickets.pop(token, None)
        if not ticket or ticket['expires'] < time.time():
            raise ValueError('预览已过期，请重新检查')
        if fingerprint() != ticket['before']:
            raise ValueError('依赖环境已变化，请重新预览')
        # Preview rejected any transitive changes. --no-deps guarantees execution
        # cannot introduce a resolver cascade after confirmation.
        p = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--disable-pip-version-check', '--no-input', *ticket['specs']], capture_output=True, text=True, timeout=600)
        actual = dict(inventory())
        verified = all(actual.get(s.split('==')[0]) == s.split('==')[1] for s in ticket['specs'])
        return {'status': 'success' if p.returncode == 0 and verified else 'failed', 'message': '核心包已安装，需重启后重新检测' if p.returncode == 0 and verified else '安装失败或版本未核实，请查看日志', 'log': (p.stdout + '\n' + p.stderr)[-10000:], 'restart_required': True}
    finally:
        _lock.release()
