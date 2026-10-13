# Godot 临时导入与录制

四方向行走、静态待机、法线和金属蒙版都通过人工审查后，填写 `delivery.template.yaml`。每方向明确颜色目录、法线目录和待机帧，四方向使用同一色板和 `[128,240]` 锚点。

```sh
h3-character assemble delivery.yaml --output output/jade-traveler-v1
h3-character verify output/jade-traveler-v1
```

独立项目只交付相对路径资源包。hd-2d-godot 的私有场景不进入开源项目；以下接入发生在游戏自己的临时演示副本中。

## 临时接入

1. 记录游戏当前 HEAD、工作区改动及默认主角资源摘要。创建忽略的独立演示副本，复制当前场景、脚本、shader 和必要资源，排除 `.git`、`.godot`、历史构建包与录制结果。若有本地游戏改动，演示副本使用实际当前字节，不把仅含 HEAD 的副本冒充当前工程。
2. 将资源包的 `character/` 复制到演示副本 `assets/characters/jade-traveler/v1/`，`normals/` 复制到 `assets/character-normals/jade-traveler/v1/`。
3. 仅在演示副本修改 `scripts/character_animation.gd` 的角色 ROOT、`scripts/pixel_actor.gd` 的初始 atlas，以及 `scripts/ancient_canal/actor.gd` 的 NORMAL_ROOT。暂时替换演示主角，不覆盖正式银饰少女文件或历史证据。
4. 核对所有贴图导入参数。运行时三种图使用同一朝向、帧索引和 atlas_region。脚底仍是世界位置原点，不移动碰撞体来修正角色贴图。
5. 运行项目适用的来源、角色合同和解析检查；既有测试若写死银饰少女 108 帧或旧路径，保留原测试，用临时角色的清单生成专用校验，不伪称全套旧验收通过。

本项目提供 `examples/stage_godot_demo.py`。它只接受已放置 `demo-source.json` 来源记录且不含 `.git` 的临时副本，要求原角色路径可识别并拒绝覆盖已经导入的角色。完整可编辑法线留在资源包；游戏只导入配对运行时图集。

```sh
python examples/stage_godot_demo.py output/jade-traveler-v1 --project .local/hd2d-demo
```

初次 Godot 导入后，检查新 PNG 的 `.import`，设 `compress/mode=0`、`detect_3d/compress_to=0`、`mipmaps/generate=false`，再导入一次。法线图不是 sRGB 颜色，shader 的 normal／mask sampler 不声明 `source_color`。编辑器配置及缓存放在副本 build 的 XDG 目录，避免改动日常 Godot 用户配置。

游戏既有扫光脚本若引用旧法线清单，在副本里改成新运行时清单，并用每方向真实帧数动态循环。颜色纹理、法线图集、金属图集、原帧路径与切片均从同一帧清单验证。图集和脚底锚点检查不应依赖银饰少女的旧PNG摘要。

## 实际画面检查

Godot 桌面实际启动江南河街场景。分别确认四方向行走、停止后的平衡待机、灯光切换、金属饰品扫光、树／建筑遮挡、桥面和岸边脚底接触。灰材质检查形体，关闭法线比较差异，关闭金属高光检查蒙版。

保留截图、工程版本、角色包摘要、实际 GPU／窗口模式和检查结论。headless、CPU 联系图和最小化离屏画面分别标明，不把它们写成用户录屏。

## 录制镜头

先保留三组原片，各镜头以 1920×1080、60 FPS 为目标，实际参数以采集验证为准：

- 四方向联系图与动画预览，直观看到独立方向和完整步态。
- 江南河街慢速探索，左右行走、桥头转向、正背面和停步。
- 夜景静止及慢走扫光，法线／灰材质／金属高光的开关对比。

录制前与用户确定操作和镜头。Godot 的确定性离线电影输出可用于展示片，但记录为离线录制，不能用它证明实时帧率。保留未剪辑视频和 FFprobe 的尺寸、帧率、时长及完整解码检查。结束后关闭演示副本，正式工程仍可运行原默认角色。
