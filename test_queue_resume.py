import asyncio
import heapq
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from queue_resume import QueueResume

class Queue:
    def __init__(self):
        self.mutex=threading.RLock();self.not_empty=threading.Condition(self.mutex)
        self.queue=[];self.currently_running={};self.server=SimpleNamespace(queue_updated=lambda:None)
    def get(self,timeout=None):return (heapq.heappop(self.queue),0) if self.queue else None
    def put(self,item):heapq.heappush(self.queue,item)

def item(n):return (n,str(n),{'node':{'class_type':'Test'}},{},['node'],{})
async def validate(*args):return (True,None,['node'],{})
async def reboot():pass

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_and_restore_once(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'snapshot.json';q=Queue();q.currently_running={0:item(5)};q.queue=[item(8),item(7)]
            interrupts=[];r=QueueResume(q,file,lambda:interrupts.append(True),reboot,validate)
            p=r.preview();await r.execute(p['token'])
            self.assertEqual(interrupts,[True]);self.assertEqual(q.queue,[])
            with self.assertRaises(RuntimeError):q.put(item(10))
            q2=Queue();r2=QueueResume(q2,file,lambda:None,reboot,validate);await r2.restore()
            self.assertEqual([x[1] for x in sorted(q2.queue)], [r2.state['snapshotId']+'-'+str(n) for n in range(3)])
            self.assertEqual([x['originalId'] for x in r2.state['restored']],['5','7','8'])
            q3=Queue();r3=QueueResume(q3,file,lambda:None,reboot,validate);await r3.restore();self.assertEqual(q3.queue,[])
    async def test_sensitive_and_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            q=Queue();r=QueueResume(q,Path(d)/'s.json',lambda:None,reboot,validate)
            q.queue=[item(1)];p=r.preview();q.queue.append(item(2))
            with self.assertRaises(ValueError):await r.execute(p['token'])
            q.queue=[(*item(1)[:5],{'api_key':'secret'})]
            with self.assertRaises(ValueError):r.preview()
    async def test_uncertain_restore_does_not_replay(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'s.json';file.write_text('{"phase":"restoring","items":[]}',encoding='utf-8')
            q=Queue();r=QueueResume(q,file,lambda:None,reboot,validate);await r.restore()
            self.assertTrue(r.paused);self.assertEqual(q.queue,[])

if __name__=='__main__':unittest.main()
