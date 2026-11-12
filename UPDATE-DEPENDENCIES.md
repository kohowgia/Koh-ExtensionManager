# 更新后的依赖处理

单个更新、一键更新、手动切换版本和清单更新在 Git 成功后复用 `_post_install_setup()`：优先调用当前 Python 下的 ComfyUI-Manager `cm-cli.py post-install`，缺少 Manager 时使用已有 fallback。

返回字段：`code_status`、`actual_commit`、`dependencies_status`、`dependencies_log`、`restart_required`。代码已切换而依赖失败时保留代码与启用状态，不自动回退、不禁用已有插件、不重启。依赖失败整体返回 error，调用方应同时展示代码成功及依赖失败。完整日志尾部保留 6000 字符。一键更新串行执行，避免同批次并发修改 Python 环境。

新装的原有流程及 pin/latest 的下载方式保持不变。不同 HTTP 请求仍需由维护者避免并发操作同一 Python 环境。

离线验证：`python test_update_dependencies.py`。测试不运行真实 Git、pip 或远程更新。
