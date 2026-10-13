# 安装、模型与环境

## 工具环境

准备 Linux x86_64、Python 3.12、Git、可运行 CUDA 13.0 PyTorch 的 NVIDIA 驱动，以及 FFmpeg。无需管理员安装项目，不修改系统 Python，不修改现有 ComfyUI。CPU 命令在项目 `.venv`，GPU 服务和抠图命令在独立 `.runtime/venv`。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/h3-character --version
```

## 模型

阅读 THIRD_PARTY.md 的模型许可，准备约 52 GB 权重空间，并另留环境和生成帧的空间。

```sh
.venv/bin/h3-character download-models --models-dir models
```

下载使用随包 `data/models.lock.json` 的固定 revision、文件大小与 SHA-256。先写 `.part`，验证后才改为正式文件。已存在但校验失败的文件不会被覆盖；网络中断时保留 `.part`，检查后将其移到备份位置再重跑。不会盲目反复下载大文件。

已有权重时，复制 `examples/model-files.template.yaml` 为忽略的 `.local/model-files.yaml`，改成自己的绝对路径。`prepare-runtime --model-files .local/model-files.yaml` 只读原文件，核对完整摘要并写入运行环境的模型搜索路径。

## 固定源码与 GPU 环境

```sh
.venv/bin/h3-character prepare-runtime --runtime .runtime --models-dir models --install-gpu
# 已有权重：额外传 --model-files .local/model-files.yaml。
make wheel
.runtime/venv/bin/python -m pip install --no-deps dist/h3_character_studio-0.1.0-py3-none-any.whl
.runtime/venv/bin/python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
```

安装器下载固定提交的 ComfyUI 和 BiRefNet，创建新环境，按随包 H3 依赖锁使用 `pip --require-hashes` 安装。CUDA wheel 源是 `https://download.pytorch.org/whl/cu130`。这些锁从实际本地流程抽取，新的电脑仍需做真实推理验证。另一份 ToonOut 历史锁仅用于来源参考，不与 H3 锁混装。

已有完整 wheelhouse 时，prepare-runtime 增加 `--wheelhouse /path/to/wheelhouse` 即可离线安装，仍核对同一哈希锁。若上游 wheel 不可下载，保留失败环境，按错误里列出的文件收集完整 wheelhouse。手工修复安装时使用 `--no-index --find-links /path/to/wheelhouse --require-hashes -r` 同一锁文件，不能随意升级版本。驱动、系统资源或网络无法自动配置时，记录实际失败与修复步骤，不把“依赖已安装”记为“模型已生成”。

源码也可以离线准备。`--source-caches .local/source-caches.yaml` 接受 `comfyui` 和 `birefnet` 两项 Git 仓库路径。安装器复制独立 Git 对象并检出固定提交，不复制工作区修改、旧 venv 或硬链接模型。已生成 runtime 重用前通过 doctor 检查，升级时使用新的 runtime 目录。

## 启动 ComfyUI

```sh
.runtime/venv/bin/h3-character serve --runtime .runtime --port 8197
# 另一个终端
.venv/bin/h3-character doctor --runtime .runtime --url http://127.0.0.1:8197 --verify-models
```

浏览器进入 `http://127.0.0.1:8197`。服务仅绑定本机，只加载项目自带两个节点，使用独立 input、output、temp、user 和数据库。默认 lowvram、reserve-vram=1、关闭预览、关闭节点缓存；不接管占用同一端口的服务。启动失败时保留日志并选一个未占用端口。

终止服务前通过 `/queue` 确认没有运行或排队作业，再在服务终端 Ctrl+C。观察命令退出不会取消 GPU 作业；不要为了重新观察而重启服务或重新提交。
