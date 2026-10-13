# 效果先行的三分钟审阅片

使用已经验收的动画和实际 GPU PNG/RGB 录像，不生成角色动画，也不修改颜色、法线或材料素材。

`timeline.json` 决定段落顺序和帧数。默认先展示夜晚漫游 10 秒、四向光照 24 秒、冷暖环绕 36 秒，再讲制作过程，总计 180 秒、5400 帧。`cards.json` 保存标题、正文与示例图来源。

```sh
.venv/bin/python examples/video/build_review.py --root .
```

输入必须显式准备在代码列出的本地制作目录：`output/jade-traveler-owned-surfaces-v8/`、`output/clean-frame-review-v8/`、历史失败样例和隔离 Godot 副本的 GPU 证据。这个剪辑示例消费本次案例的真实素材，不能冒充运行 H3 后自动得到完全相同的影片。游戏世界本身不在开源包中。

字体为 jibijibi-game 当前主界面及 HUD 使用的 Z Labs Pixel 12px 简体中文，原文件、来源 SHA256 和 SIL OFL 原文保留在 `fonts/`。原生 12px 单色字形用最近邻整数放大：主标题 60px、正文 36px、命令／图注 24px；镜头标题 36px、进度条标题 24px。检查实际文字覆盖，不使用字体回退。

底部 overlay 高 92px，范围为 `[0,988,1920,92]`。段落宽度按实际时长分配，过去段落为青绿、当前进度为暖金、未来段落为暗灰。当前标题位于条上方，右侧显示时间。按帧索引计算，段落切换与 30FPS 影片严格一致；它是影片中的显示层，不是可拖动播放器控件。

先从 PNG 或 RGB 无损母版制作标题、局部放大和字幕，再保存 RGB 无损成片。MP4 是播放副本；不从有损影片二次放大角色。既有 v8 原片与剪辑保持独立，新稿写入 `output/video-technical-v10-review/`。

四向白光 v10 已在实际 GPU 中把点光强度从 1.8 降为 0.7；环境光始终为 0。顶部和底部随当前方向高亮，上方金黄、下方蓝、左侧青绿、右侧珊瑚红，并保留方向文字。独立四向片包含自己的四段进度 overlay。

可用 `--cardinal-capture .local/hd2d-demo/build/ancient-canal/jade-cardinal-v10 --reuse-review output/video-technical-v9-review` 显式复用上一版不变的 RGB 无损镜头。文字卡只有在新旧 PNG 摘要相同后才复用，来源写入剪辑配方。

[实际 GPU 调参台](lighting-control/README.md)提供实时参数、固定帧比较和显式保存。预览与录像共用场景与参数应用函数；保存文件驱动录像和动态时长剪辑。

卡片可设置 `subtitle`、`source` 与逐图 `image_notes`。字幕来源、用途及片尾“三连”动画记录在剪辑配方。片尾沿用原 4 秒，使用原生像素文字动画；全片维持 180 秒。

`add_audio.py` 可将用户提供的音乐加入已验证 MP4：双遍响度、长度对齐与首尾淡入淡出，视频轨直接复制并检查完整码流哈希。音频不进入源码包，细节见剪辑 runbook。

最新底部样式为原青绿／暖金／暗灰连续分段框，24px 短标题在框内，上方附简短说明。`short_title` 控制文案；段宽保证标签可读后按时长分配，当前填充按帧推进。`--orbit-review` 可显式使用已确认的环绕 RGB 原片。
