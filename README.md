# H3 character studio

从四方向角色母版与提示词生成 H3 动画，保留原始帧，用 ToonOut 抠图并直接导出 256×256 像素序列，再绘制逐帧几何法线和金属材质蒙版。

这是从 AssetWorkbench 和 hd-2d-godot 角色制作流程抽取的独立 Python 项目。运行时不需要这两个源码仓库，不包含工作台网页、VGP 或游戏场景。来源文件与摘要见 [SOURCE.json](SOURCE.json)。

第一版使用 Linux x86_64、Python 3.12、NVIDIA CUDA 13.0 环境。CPU 工具、独立 wheel 安装和素材合同测试与真实 GPU 推理分别验收，当前状态见 [制作记录](docs/production-status.md)。H3 权重约 50.92 GB，加 ToonOut 约 0.89 GB；下载前另留软件、缓存和输出空间。设备最低要求以实际推理为准，不承诺任意 GPU 都可运行。

青绿少女四方向已实际生成，256动画、108帧法线和金属蒙版已在Godot GPU验证，制作实录见 [青绿少女案例](docs/jade-traveler-production.md)。模型推理具有随机性，提示词和来源摘要用于追踪，不承诺不同设备生成相同像素。游戏演示和视频不会改变正式主角。

最新视频采用效果先行的三分钟结构、jibijibi-game 像素字体和分段进度 overlay。新增实际 GPU 交互调参和保存工具；当前四向片使用用户选定的点光 2.65、环境光 0，动画以 1× 正常行走，当前方向以四种颜色高亮，见 [剪辑 runbook](docs/runbooks/06-editing.md)。冷暖环绕已按用户确认的新参数替换，底部采用原配色分段框，短标题在框内、上方附说明。制作页注明实际模型／工作流来源与失败／纠正环节，素材图分别解释用途；片尾含像素文字“三连”动画。

## 安装与使用

```sh
make install
.venv/bin/h3-character --help
# 首次从上游下载固定版本与固定摘要的权重。
# 默认模型目录 ~/Models/shared，可与 Asset Workbench 共用
.venv/bin/h3-character download-models
# 公共目录中已有的权重会通过摘要校验后直接复用。
.venv/bin/h3-character prepare-runtime --runtime .runtime --install-gpu
make wheel
.runtime/venv/bin/python -m pip install --no-deps dist/h3_character_studio-0.1.0-py3-none-any.whl
.runtime/venv/bin/h3-character serve --runtime .runtime
```

完整操作按以下顺序执行：

1. [安装、模型与环境](docs/runbooks/01-install.md)。
2. [互动设计与四方向母版](docs/runbooks/02-character-design.md)。
3. [ComfyUI 生成、选帧与 256 导出](docs/runbooks/03-generation.md)。
4. [法线自动绘制、材质蒙版与修订](docs/runbooks/04-normals.md)。
5. [Godot 临时导入与视频录制](docs/runbooks/05-godot-video.md)。
6. [剪辑与文案协作](docs/runbooks/06-editing.md)。

新增逐帧脸部与银饰标注接口，详见 [外部块与像素归属](docs/topics/foreground-and-material-ownership.md)。用户已确认鼻部与脸颈外部块修复并要求采用；其余美术细节仍独立审查，最新代码和视频尚未推送。

最新三分钟审阅片先展示效果，加入上下左右光照和分段进度 overlay；复用 jibijibi-game 当前像素字体，标题与正文分级。可编辑剪辑示例见 [视频制作入口](examples/video/README.md)。

讲解重点：[逐帧输出通过，衣物为什么仍像平面](docs/topics/clothing-normals.md)，记录银饰少女精度对照、重绘与实际受光检查。

## 输入与产物

`character.yaml` 接受角色 ID、四方向参考 PNG、各方向提示词或提示词文件、种子、H3 帧数与采样参数。母版可以是高分辨率 RGBA 图，ComfyUI 统一投影到 768×768。四方向独立生成，左右和背面都不镜像代替。示例格式见 [角色配置](examples/jade-traveler/character.template.yaml)。

每个作业保留冻结母版、完整配方、提示词、真实节点规格、可在 ComfyUI 导入的工作流、API 图、prompt ID 和历史。每个方向只提交一次；`resume` 查询原作业。原始帧、抠图软蒙版、恢复 RGB、透明帧、统一色板、256 序列、图集、时长与来源索引分别保存。

法线绘制需要新角色的关键姿态形体标注。工具双向传播标注、计算解析曲面的向量并生成材质蒙版；每帧保留可编辑几何、标签和向量层。未知区域、遮挡和循环接缝需要审查。颜色亮度不作为高度或法线来源。

四方向采用同一色板和脚底锚点，输出 Godot 可读的 `character.json` 和颜色／法线／材质图集。静态待机帧由制作人明确选择。技术校验不会自动批准角色美术或修改游戏。

## 开源内容

本项目代码与文档采用 MIT，保留抽取代码的许可与来源。ComfyUI、BiRefNet 及模型使用各自许可，见 [第三方说明](THIRD_PARTY.md)。权重通过固定来源下载，不进入源码包。示例包含用户选定的双马尾青绿少女、四方向母版、实际提示词和可编辑形体标注。银饰少女原 PNG、私有游戏世界素材和运行日志不进入公开项目。
