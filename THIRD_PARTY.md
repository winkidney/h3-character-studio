# 第三方与来源

本项目独立代码与文档使用 MIT。保留 AssetWorkbench 仓库原有 [MIT 许可](third_party/asset-workbench-LICENSE)，并在 SOURCE.json 记录抽取时的提交、工作区状态和文件摘要。AssetWorkbench 抽取时存在未提交修改，因此提交号不是全部来源的证明，文件摘要才标明本次使用的实际字节。

- ComfyUI 固定提交 `a8686f2b33fc540f137df50c0f0719953830a5e7`，独立下载至运行环境，保留上游 [LICENSE](https://github.com/Comfy-Org/ComfyUI/blob/a8686f2b33fc540f137df50c0f0719953830a5e7/LICENSE)。
- BiRefNet Comfy 节点固定提交 `5443a2aa16cfbd98bb2f7dcc8bdcb70439e08529`，安装时保留[上游仓库](https://github.com/lldacing/ComfyUI_BiRefNet_ll)的许可文件。
- H3 三份权重固定于 `Comfy-Org/MiniMax-H3`，使用 [MiniMax H3 社区许可](https://huggingface.co/Comfy-Org/MiniMax-H3)。本项目的 MIT 许可不覆盖这些权重；具体使用和再分发条件读取上游协议。
- ToonOut 固定于 `joelseytre/toonout`，模型页标注 [MIT](https://huggingface.co/joelseytre/toonout)。文件路径、版本、大小与 SHA-256 随包保存。
- 几何向量、光流传播与法线编码函数来自用户本地 hd-2d-godot 角色制作工具。游戏场景、原角色图片和 SpriteLamp 移植 shader 未打包。新工具使用外部形体 YAML，未复制银饰少女专用的坐标和衣色分类。

模型页与许可链接于 2026-10-13 核对。发布物不包含模型、ComfyUI 源码、私有游戏或本机绝对路径配置；这些依赖在使用者机器上单独准备。示例候选由内置 ImageGen 生成，回执不虚构可指定的模型版本或种子，也不保证相同提示词能重现相同像素。
