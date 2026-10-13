# ComfyUI 生成与动画提取

## 冻结输入

银饰少女流程的参数基线是 768×768、56 帧、24 FPS、40 步、simple scheduler、res_multistep sampler；首尾使用同一方向母版，27 帧处可加入同一母版作为中间引导。H3 合法帧数为 `17k+5`，最少 22。新角色先测试 right 方向，确认运动和设计后逐方向串行制作。

动画提示词同时写明身份、朝向、步态、附属物和排除项。例如：

```text
The exact traveler from this direction reference. Preserve face, proportions,
two high unbraided ponytails, jade ornaments, cream capelet, green garment layers and woven borders,
plum sash, silver hair cuffs, cape brooch, wrist cuffs, waist pendants, strap route and leather satchel attachment.
Fixed mildly elevated orthographic [DIRECTION VIEW]; pelvis, knees and shoes face [DIRECTION].
Walk IN PLACE continuously from first to last frame, constant moderate cadence,
two complete walking cycles in 2.33 seconds. Alternate grounded contact, support,
passing and push-off; arms swing opposite the legs. Keep root and ground reference stable.
No starts, stops, idle pauses, running, turning or movement across the canvas.
Both ponytails, capelet, skirt and waist pendants follow the step with small gravity-driven delay.
The satchel remains attached, with restrained swing; rigid silver cuffs and brooch do not bend.
Stable crisp pixel contours, woven motifs and colors. No morphing or invented ornaments.
Uniform solid #ff00ff magenta background, no ground drawing, shadow, environment,
camera motion, zoom, cuts, captions, extra limbs or objects.
```

正面强调双眼和胸口朝观察者，手脚在深度方向摆动；背面强调不露脸、不出现胸饰；侧向强调髋、膝和鞋朝对应侧。提示词不是循环已经无缝的证明。

背面首轮 `up-001` 失败：原提示词前段包含眼睛、脸型和胸前饰物，后段虽排除正面，模型仍把大多数中间帧生成正面。保留完整作业和联系图，禁止从少数背面引导帧拼成假动画。修订 `prompts/up-v2.txt` 只描述后脑、背披肩、后裙与背向步态，移除正面身份词；`character-up-v2.yaml` 使用新种子 442，并在 13、27、41 帧串联背面母版引导。额外引导可能造成停顿，生成后必须重新检查连续步态；提交成功不表示修订通过。实际最终结果另记制作状态。

```sh
h3-character prepare examples/jade-traveler/character.yaml --direction right --output runs/right-001
h3-character run runs/right-001 --observe-seconds 30
h3-character resume runs/right-001 --observe-seconds 30
```

prepare 不提交生成，先保存冻结母版、配方、提示词、API 图与真实节点规格，上传唯一文件名。可打开生成的 `workflow.json` 检查节点。正式 CLI run 与手动点击 ComfyUI Queue 二选一，同一目录不要混用；手动运行会绕过 CLI 的提交回执，必须保存其 prompt ID 和 history。

提交之前写入 `submission_unknown`，返回 prompt ID 后再记为 queued。响应丢失时 resume 按唯一 run ID 在队列／历史查找，不重新提交。服务重启或历史被清除时保留 unknown 并调查。输入更改、重试生成、修改种子都使用新 run，不覆盖原证据。

## 抠图与统一色板

GPU 作业完成后，原始帧在 `.runtime/output/h3-character/RUN_ID`。输出节点核对 56 帧并释放生成模型。以下抽取命令必须使用 GPU 环境中的同一项目 wheel。

```sh
h3-character palette examples/jade-traveler/masters/right.png --output runs/palette.json --colors 96
.runtime/venv/bin/h3-character extract .runtime/output/h3-character/RUN_ID \
  --runtime .runtime --palette runs/palette.json --output runs/right-001-extracted
h3-character review runs/right-001-extracted/pixel-256 --output runs/right-001-review
```

四方向统一使用 `runs/palette.json`，不逐帧取新色板。ToonOut 使用固定模型、1024 输入、float32、batch=1、软蒙版保留 16 位；pymatting 恢复前景 RGB，0.5 阈值生成硬 Alpha，默认不腐蚀和不补插帧。从原始 768 帧按同一完整画幅最近邻采样到 256，再映射共享色板。默认脚底锚点 `[128,240]`，实际视觉复核后固定；禁止逐帧自动居中破坏步态。

已人工完成高分辨率硬 Alpha 的序列可以用 `--prepared-rgba`，它不会伪称运行过 ToonOut。

## 选完整循环

查看全部联系图及动画，检查脸与衣饰、左右脚接触、双脚交替、发辫滞后、包带连接、裙褶、根部漂移和首尾接缝。保留失败方向并用新作业修正，尤其背面不能用正面饰品伪装。

银饰少女曾从 56 帧中选择连续 27 帧，不跳帧、不补帧、不改变速度；这是该作业的选择结果，新角色不照搬同一索引。用户／制作人确认本次完整步态区间后：

```sh
# 例子：[28,55)，包括原帧28至54。索引以本次审查为准。
h3-character select runs/right-001-extracted/pixel-256 --start 28 --stop 55 --output runs/right-001-selected
```

颜色输出含全部帧、图集、每帧毫秒时长、原始帧索引、透明边界及摘要。技术通过之后仍需确认视觉；待机从平衡、不悬空、衣饰稳定的帧中单独选择。
