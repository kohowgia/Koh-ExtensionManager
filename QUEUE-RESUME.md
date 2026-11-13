# 保留任务重启（实验功能）

只覆盖主动触发的重启，不是生成中断点续算，也不是崩溃容灾。当前实现适配六字段 PromptQueue 元组；其他格式明确拒绝。运行中任务从头运行，可能重复文件写入和付费 API 副作用。

## 流程

POST `/extension_manager/queue_resume/preview` 返回 60 秒 token、运行/排队数量。预览不改变任务。POST `/extension_manager/queue_resume/execute` 带 token、`confirmReplay:true`：在队列锁内检查完整快照未变化，暂停队列消费和新提交，原子保存运行中优先+排序后的待执行任务，清空等待队列，发 interrupt，延时一秒 execv。保存失败不会中断任务。普通重启保持原行为。

队列快照保存在 user/koh_queue_resume/<hostname-port>/snapshot.json。共享 user 目录的实例必须具有不同 hostname-port，或设置唯一且稳定的 KOH_QUEUE_INSTANCE_ID。容器重建导致 hostname 变化时不会自动找到旧快照，需人工处理；本功能使用 execv，不重建容器。

启动 on_startup 在节点注册后重新 validate_prompt，给任务生成快照派生的新 ID，保留原工作流/seed/提交者信息。无效任务写 errors，其他任务继续。恢复状态先落盘再入队，防止重启重放：若进程在该边界再次崩溃，可能需要人工找回未入队任务，不能保证 exactly-once。状态为 restoring 的快照不自动重放。

GET `/extension_manager/queue_resume/status` 只返回状态/计数/ID映射/错误，不返回工作流负载。异常暂停可人工核查后 POST `/extension_manager/queue_resume/release`，携带 snapshotId 和 confirmReviewed:true；只解除暂停不提交任务。

## 边界

不保存媒体历史、输出资产或临时输入文件。文件清理后任务可验证失败，或在实际执行时失败。六字段敏感凭据槽非空时拒绝快照；自定义节点嵌在普通输入中的秘密不能自动识别，快照按私有文件权限保存，勿共享/上传该文件。Windows 权限依赖已有 user 目录 ACL。远程接口继承现有 ComfyUI 的访问控制，仅限可信管理网络。

恢复成功快照暂保留以便人工核查，不无限积累（下一次覆盖同一实例文件）。不要在恢复失败未核查时发起新快照，以免丢失待处理项。`python test_queue_resume.py` 使用模拟队列，不调用真实 reboot/pip。
