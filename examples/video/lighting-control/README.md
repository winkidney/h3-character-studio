# 实际 GPU 光照调参台

本地网页调节四向点光、环境光、法线强度、灯位、灯距、范围、动画倍率和停留时间。原色与灰材质共用姿态，预览通过已准备的隔离 Godot 项目实际渲染。此示例需要 `scenes/ancient_canal.tscn` 的角色适配器和 `tools/project.py`；游戏世界不包含在公开包中。它不是运行 H3 的必要依赖。

```sh
.venv/bin/python examples/video/lighting-control/serve.py \
  --godot-project .local/hd2d-demo --state output/lighting-control
```

打开 `http://127.0.0.1:18793`。使用 jibijibi-game 的 Z Labs 像素字体，方向按钮与当前方向标签分别为金黄、蓝、青绿、珊瑚红。只监听本机，同源校验保护写入接口。没有 CDN 或外部网络依赖。

固定动画帧可在同一姿态比较四个方向。环境光控制暗部底光，点光强度控制移动光源。默认环境光 0、点光 0.7、法线 0.8；不修改色图、法线图或材质蒙版。自动切换按上、下、左、右循环，每段开头使用 0.8 秒平滑过渡。

调参只更新 `current.json`。等待新参数对应的 GPU 画面显示，再点击“保存并用于后续录像”。界面把渲染版本与画面序号交给保存接口，拒绝旧画面、未应用的参数及越界值。保存生成 `selected.json`、带时间的历史 JSON 和用户当时看到的 PNG，记录截图 SHA256 与实际适配器／渲染器。再次调参不改变已保存选择；重启恢复最后保存的参数。

保存后录制：

```sh
.venv/bin/python examples/video/lighting-control/record_saved.py \
  --godot-project .local/hd2d-demo \
  --selection output/lighting-control/selected.json \
  --output output/cardinal-user-selected
```

用户要求正常行走速度时，录制命令增加 `--playback-scale 1`。只覆盖录像速度，保留用户原始保存参数及明确覆盖记录；不会回写界面的选择文件。

预览与录像共享 `cardinal_scene.gd`，同一参数应用函数、相机和素材。录制开始先冻结选择文件副本；灯光参数、动画倍率和每向停留时间直接读取保存值。单向按钮、暂停和固定帧属于比较操作，正式录像按四向连续走动。30FPS、1920×1080 PNG；结束检查实际参数一致性、双视口帧同步和有效帧数，输出 `shot-recipe.json` 的 `source_start_frame` 和 `source_frames`。

合成选定参数的影片：

```sh
.venv/bin/python examples/video/build_review.py \
  --cardinal-capture output/cardinal-user-selected \
  --reuse-review output/video-technical-v10-review \
  --output output/video-user-selected
```

剪辑读取真实轨迹帧数，同步调整方向高亮、独立进度条、整体时间线及影片时长，保存选择写入剪辑配方。改变每向停留时间后，不再假定四向片长 24 秒。非四向片段复用既有 RGB 无损来源；历史输出保留。公开示例不包含此次完整影片或游戏场景。

服务终止时同时退出其预览 Godot 进程，保留保存记录。制作机器需已有图形会话和实际 GPU；不能把 headless 启动成功当作视觉验证。
