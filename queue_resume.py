"""Planned restart queue recovery. Never resume GPU execution state.
A claimed snapshot is never replayed after another process failure: fail closed.
Sensitive queue payloads are rejected rather than persisted as plaintext.
"""
import asyncio
import copy
import hashlib
import heapq
import json
import os
from pathlib import Path
import secrets
import threading
import time

class QueueResume:
    def __init__(self, queue, file, interrupt, reboot, validate):
        self.q, self.file = queue, Path(file)
        self.interrupt, self.reboot, self.validate = interrupt, reboot, validate
        self.state = self.read()
        if self.state.get('phase') == 'restoring':
            self.state.update(phase='blocked', message='上次恢复中断，任务是否执行不确定；已暂停，需人工核查，不能自动重放')
        self.paused = self.state.get('phase') in ('saved', 'restoring', 'blocked')
        self.tickets = {}
        self.original_get, self.original_put = queue.get, queue.put
        def get(timeout=None):
            # Protect the check/pop boundary with the same mutex as capture.
            deadline = time.monotonic() + (timeout if timeout is not None else 1000)
            while True:
                with queue.mutex:
                    if not self.paused and queue.queue:
                        return self.original_get(timeout=0)
                if time.monotonic() >= deadline:
                    return None
                time.sleep(.1)
        def put(item):
            with queue.mutex:
                if self.paused:
                    raise RuntimeError('实例正在保存或恢复重启队列，请稍后提交')
                return self.original_put(item)
        queue.get, queue.put = get, put

    def read(self):
        if not self.file.exists(): return {'phase': 'idle'}
        try:
            state = json.loads(self.file.read_text(encoding='utf-8'))
            if not isinstance(state, dict): raise ValueError('invalid state')
            return state
        except Exception:
            return {'phase': 'blocked', 'message': '任务快照无法读取，已暂停自动恢复，请人工核查'}

    def save(self, state):
        self.file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.file.parent, 0o700)
        temp = self.file.with_suffix('.tmp')
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, self.file)
        self.state = state

    def items(self):
        return copy.deepcopy(list(self.q.currently_running.values()) + sorted(self.q.queue, key=lambda x:x[0]))

    def digest(self, items):
        return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()

    def status(self):
        # No prompt graph, file paths, or execution secrets in status responses.
        return {k:v for k,v in self.state.items() if k in ('phase', 'snapshotId', 'createdAt', 'runningCount', 'pendingCount', 'restored', 'errors', 'message')} | {'paused': self.paused}

    def release(self, snapshot_id):
        """Explicit escape hatch after manual review, never resubmit tasks."""
        with self.q.mutex:
            if self.state.get('phase') not in ('blocked', 'restoring', 'restored') or snapshot_id != self.state.get('snapshotId'):
                raise ValueError('仅可解除已核查的异常恢复状态')
            self.save({**self.state, 'phase':'released', 'reviewedErrors': self.state.get('errors', []), 'errors': [], 'message':'人工解除维护暂停；备份保留，未重新提交任务'})
            self.paused = False
            self.q.not_empty.notify_all()
        return self.status()

    def preview(self):
        with self.q.mutex:
            if self.paused or self.state.get('errors'): raise ValueError('已有保存、恢复异常或失败任务，请先核查快照再操作')
            items = self.items()
            # ComfyUI currently stores sensitive API keys in slot 5. Also refuse
            # unknown tuple formats: never silently lose credential/state fields.
            for item in items:
                if len(item) != 6 or item[5]:
                    raise ValueError('队列包含敏感凭据或不支持的任务格式，不能自动保存恢复')
            payload = json.dumps(items).encode()
            if len(payload) > 50 * 1024 * 1024: raise ValueError('任务快照超过 50 MB，请减少队列后重试')
            token = secrets.token_urlsafe(24)
            self.tickets = {token: (time.time()+60, self.digest(items))}
            return {'token':token, 'running':len(self.q.currently_running), 'pending':len(self.q.queue), 'bytes':len(payload)}

    async def execute(self, token):
        with self.q.mutex:
            ticket = self.tickets.pop(token, None)
            if not ticket or time.time()>ticket[0] or self.paused: raise ValueError('确认已过期，请重新检查')
            items = self.items()
            if self.digest(items)!=ticket[1]: raise ValueError('队列已变化，请重新确认')
            self.paused = True
            try:
                self.save({'phase':'saved', 'snapshotId':secrets.token_hex(16), 'createdAt':time.time(), 'items':items, 'runningCount':len(self.q.currently_running), 'pendingCount':len(self.q.queue)})
            except Exception:
                self.paused = False
                raise
            # Snapshot is durable before interrupt or removal of the pending list.
            self.q.queue.clear()
            self.q.server.queue_updated()
            self.interrupt()
        # Give the HTTP acknowledgement a chance to flush; execute exactly once.
        async def restart_later():
            await asyncio.sleep(1)
            try: await self.reboot()
            except Exception as exc:
                self.save({**self.state, 'phase':'blocked', 'message':'重启未完成：'+str(exc)})
        asyncio.create_task(restart_later())
        return self.status()

    async def restore(self, app=None):
        if self.state.get('phase') != 'saved':
            return
        with self.q.mutex:
            if self.q.queue or self.q.currently_running:
                self.save({**self.state,'phase':'blocked','message':'启动时已有任务，拒绝混合恢复'})
                return
            state = {**self.state,'phase':'restoring'}
            self.save(state)  # A crash from here onward requires manual review.
        restored, errors, prepared = [], [], []
        try:
            for order, raw in enumerate(state.get('items', [])):
                item = list(raw)
                old_id = item[1]
                new_id = state['snapshotId'] + '-' + str(order)
                try:
                    valid = await self.validate(new_id, item[2], item[4])
                    if not valid[0]: raise ValueError(str(valid[1]))
                    item[0], item[1], item[4] = order, new_id, valid[2]
                    prepared.append(tuple(item))
                    restored.append({'originalId':old_id,'promptId':new_id})
                except Exception as exc:
                    errors.append({'originalId':old_id,'message':str(exc)[:1500]})
            # Commit the consumed marker BEFORE enqueue. A crash in this small
            # window may require manual recovery, but cannot auto-run twice.
            self.save({**state,'phase':'restored','restored':restored,'errors':errors,'message':'队列已恢复；运行中的任务从头执行'})
            with self.q.mutex:
                for item in prepared: heapq.heappush(self.q.queue,item)
                self.q.server.number = max(getattr(self.q.server, 'number', 0), len(prepared))
                self.paused = False
                self.q.not_empty.notify_all()
                self.q.server.queue_updated()
        except Exception as exc:
            self.save({**self.state,'phase':'blocked','message':'恢复中断，请人工核查：'+str(exc)})
