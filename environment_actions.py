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

def resolved_versions(names):
    """Resolve metadata in a fresh interpreter with ComfyUI's search path.
    Avoid sorted inventory -> dict, which can select a shadowed old dist-info.
    This verifies metadata resolution, not already-imported module objects.
    """
    script = "import sys,json,importlib.metadata as m; d=json.load(sys.stdin); sys.path[:]=d['paths']; out={};\nfor name in d['names']:\n try: out[name]=m.version(name)\n except m.PackageNotFoundError: out[name]=None\nprint(json.dumps(out))"
    result = subprocess.run([sys.executable, '-c', script], input=json.dumps({'names': list(names), 'paths': sys.path}), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('无法核验安装版本：' + result.stderr[-1000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


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
    installed = resolved_versions(canonicalize_name(i['metadata']['name']) for i in raw.get('install', []))
    requested = {s.split('==')[0] for s in specs}
    changes = []
    for item in raw.get('install', []):
        name = canonicalize_name(item['metadata']['name'])
        version = item['metadata']['version']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,150}', name) or not re.fullmatch(r'[0-9][A-Za-z0-9.!+_-]{0,79}', version):
            raise ValueError('安装方案包含不支持的包名或版本')
        changes.append({'name': name, 'version': version, 'installed': installed.get(name), 'direct': name in requested})
    # Confirm the complete resolver plan, including companion dependencies. Pin
    # every changed package and disable further resolution during execution.
    specs = list(dict.fromkeys(specs + [c['name'] + '==' + c['version'] for c in changes]))
    token = secrets.token_urlsafe(24)
    if len(_tickets) > 100:
        _tickets.clear()
    _tickets[token] = {'specs': specs, 'before': before, 'expires': time.time() + 600}
    return {'token': token, 'executable': True, 'changes': changes, 'message': '安装所选核心包及下列配套依赖，全部固定为确认的版本；不会自动重启。'}

def execute(token):
    if not _lock.acquire(blocking=False):
        raise ValueError('依赖处理正在执行')
    try:
        ticket = _tickets.pop(token, None)
        if not ticket or ticket['expires'] < time.time():
            raise ValueError('预览已过期，请重新检查')
        if fingerprint() != ticket['before']:
            raise ValueError('依赖环境已变化，请重新预览')
        if 'uninstall' in ticket:
            p = subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', '--disable-pip-version-check', *ticket['uninstall']], capture_output=True, text=True, timeout=300)
            actual = resolved_versions(ticket['uninstall'])
            verified = all(actual.get(n) is None for n in ticket['uninstall'])
            return {'status': 'success' if p.returncode == 0 and verified else 'failed', 'message': '包已卸载，需重启后重新检测' if p.returncode == 0 and verified else '卸载失败或版本未核实，请查看日志', 'log': (p.stdout + '\n' + p.stderr)[-10000:], 'restart_required': True}
        # All resolver changes were included and pinned in the confirmation.
        # --no-deps prevents introducing any additional unpreviewed packages.
        p = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--disable-pip-version-check', '--no-input', *ticket['specs']], capture_output=True, text=True, timeout=600)
        actual = resolved_versions(s.split('==')[0] for s in ticket['specs'])
        verified = all(actual.get(s.split('==')[0]) == s.split('==')[1] for s in ticket['specs'])
        return {'status': 'success' if p.returncode == 0 and verified else 'failed', 'message': '核心包已安装，需重启后重新检测' if p.returncode == 0 and verified else '安装失败或版本未核实，请查看日志', 'log': (p.stdout + '\n' + p.stderr)[-10000:], 'restart_required': True}
    finally:
        _lock.release()


def align_plan(items):
    """Preview explicit target versions from a trusted same-image reference."""
    if not isinstance(items, list) or not items or len(items) > 100:
        raise ValueError('请选择不超过 100 个对齐包')
    specs=[]
    for item in items:
        name=canonicalize_name(str(item.get('name','')))
        version=str(item.get('version',''))
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,150}',name) or not re.fullmatch(r'[0-9][A-Za-z0-9.!+_-]{0,79}',version):
            raise ValueError('对齐包名或版本无效')
        specs.append(name+'=='+version)
    if len({x.split('==')[0] for x in specs}) != len(specs):
        raise ValueError('对齐包重复')
    before=fingerprint()
    with tempfile.TemporaryDirectory(prefix='koh-pip-align-') as folder:
        report=os.path.join(folder,'report.json')
        proc=subprocess.run([sys.executable,'-m','pip','install','--dry-run','--report',report,'--disable-pip-version-check','--no-input',*specs],capture_output=True,text=True,timeout=300)
        if proc.returncode:
            raise ValueError((proc.stdout+'\n'+proc.stderr)[-6000:])
        with open(report,encoding='utf-8') as f:
            raw=json.load(f)
    if before != fingerprint():
        raise ValueError('检查过程中依赖环境已变化，请重试')
    direct={x.split('==')[0] for x in specs}
    installed=resolved_versions(canonicalize_name(i['metadata']['name']) for i in raw.get('install',[]))
    changes=[]
    for item in raw.get('install',[]):
        name=canonicalize_name(item['metadata']['name']); version=item['metadata']['version']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,150}',name) or not re.fullmatch(r'[0-9][A-Za-z0-9.!+_-]{0,79}',version):
            raise ValueError('对齐方案包含不支持的包')
        changes.append({'name':name,'version':version,'installed':installed.get(name),'direct':name in direct})
    specs=list(dict.fromkeys(specs+[c['name']+'=='+c['version'] for c in changes]))
    token=secrets.token_urlsafe(24)
    if len(_tickets)>100:
        _tickets.clear()
    _tickets[token]={'specs':specs,'before':before,'expires':time.time()+600}
    return {'token':token,'executable':True,'changes':changes,'message':'将目标实例的所选包对齐到参照版本；完整变更均已固定，不会自动重启。'}


def uninstall_plan(items):
    if not isinstance(items, list) or not items or len(items) > 20:
        raise ValueError('请选择不超过 20 个卸载包')
    names=[]
    for item in items:
        name=canonicalize_name(str(item.get('name','')))
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,150}',name):
            raise ValueError('卸载包名无效')
        names.append(name)
    if len(set(names))!=len(names): raise ValueError('卸载包重复')
    actual=resolved_versions(names)
    missing=[n for n in names if actual.get(n) is None]
    if missing: raise ValueError('以下包未安装：'+', '.join(missing))
    token=secrets.token_urlsafe(24)
    if len(_tickets)>100:_tickets.clear()
    _tickets[token]={'uninstall':names,'before':fingerprint(),'expires':time.time()+600}
    risks=[]
    for n in names:
        consumers=[c for c in analyze(n)['consumers'] if c.get('active')]
        if consumers: risks.append({'name':n,'consumers':consumers})
    return {'token':token,'executable':True,'changes':[{'name':n,'installed':actual[n],'action':'uninstall'} for n in names],'risks':risks,'message':'卸载会移除这些 Python 包；不会自动卸载依赖它的插件，也不会自动重启。'}
