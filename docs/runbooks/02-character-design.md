# 互动设计与四方向母版

先选定角色设计，再制作四方向。第一稿是 `examples/jade-traveler/concepts/right-v1.png`。用户要求保留整体、增加金属饰品并改双马尾，修订稿保存为 `right-v2.png`。用户于 2026-10-13 明确回复“用这一稿继续”，将其选为本次设计。

## 设计要点

第一稿参考银饰少女的头身比例、轻微俯视正交镜头和像素轮廓，改为江南行旅少女。深棕单辫、玉叶发饰、米白短披肩、青绿衣裙、梅红腰带、铜扣和皮包形成清楚的材质分组。先确认脸、头身比例、颜色、服饰层次与饰品连接点；一次只调整一类问题，保存每个候选及反馈。

2026-10-13 修订加入两束独立高马尾、银质发圈与玉叶小坠、披肩扣、腕环、腰饰及三枚挂坠、包扣和鞋扣。所有金属都保留机械连接点；衣料刺绣与玉石不计入金属蒙版。修订全文保存为 `concepts/right-v2.prompt.txt`。

交互完成后，补记最终设计选择、每轮修改、最终母版摘要和实际提示词。ImageGen 不提供本流程可指定的种子，回执使用 `null`，不把生成式母版写成像素可复现素材。

## 母版要求

- 一张 PNG 只含一名完整角色，RGBA 真透明，无地面、投影、文字或环境。画面居中，角色高度约 82%，头发、饰品、鞋子保留安全边距。
- 高分辨率母版保留清楚的像素簇与分层阴影，最终从 H3 高分辨率原始帧直接加工 256，禁止先做 64／128 再放大。
- 四方向单独绘制。down 正面朝屏幕下；up 背面朝屏幕上；left／right 为一致轻微俯视的三分之四视图，髋、膝、鞋朝对应侧，脸和身体不背离。
- 包、发辫、衣扣固定在同一身体位置。背面呈现实际后领、披肩、背带和发辫，不画正面脸、胸扣或不可见饰品。左右不能镜像代替有不对称设计的角色。
- 输入使用主动行走接触姿态，双鞋可分辨，手臂轻微反向摆动。母版、镜头、比例和留边先一致，再提交视频生成。

## 提示词

本次第一稿实际全文保存在 `concepts/right-v1.prompt.txt`。下面是定稿后制作其他方向的模板，身份段必须按最终采用图改写。

```text
Use the selected traveler image as the identity and material reference.
Preserve her exact face, body proportions, two high unbraided ponytails, jade leaf hair ornaments,
cream capelet, jade-green wrap blouse, teal pleated skirt, plum sash,
engraved silver hair cuffs, cape brooch, wrist cuffs, waist pendants,
cross-body leather satchel, silver bag clasp and dark traveling boots.
Preserve garment layers, large woven motifs, strap route and attachment points.
Create ONE full-body [FRONT / BACK / THREE-QUARTER LEFT / THREE-QUARTER RIGHT] master.
Fixed mildly elevated orthographic view. The pelvis, knees and shoes face [DIRECTION].
Active moderate walk contact pose, opposing small arm swing and separated boots.
For the back view, show the actual back construction; no visible front face or chest brooch.
Crisp dimensional pixel-art clusters, stable colors, restrained upper-left highlights.
Full character about 82 percent of a square canvas, safe clear margins.
Actual transparent background, no floor or cast shadow, no text, no duplicate characters,
no extra limbs, no generic costume simplification, no blurred or airbrushed outline.
```

准备 `masters/down.png`、`up.png`、`left.png`、`right.png` 后，复制 `character.template.yaml` 为 `character.yaml`，填入各方向动画提示词。用户确认四方向身份与朝向后运行 `h3-character validate character.yaml`。缺母版时命令失败，不偷偷用占位图或镜像补齐。

## 本次四方向与输入布局

正面、背面和左向均由内置 ImageGen 基于选定右向图独立绘制，实际提示词保存在 `masters/<direction>.prompt.txt`。包固定在角色身体右侧，背带从左肩来：正面包在画面左，背面包在画面右，左向主要呈现被身体遮挡的包边。四方向原图、回执、输入布局和联系图全部保留。

母版统一布局只做一次，不对动画每帧居中。按原图实体 Alpha 至少 128 的范围测量人物高度，最近邻缩放到 768 画布中的 648 像素高，脚底线设为 720，对应最终 256 帧的 240。躯干水平参考点由本次图形测量明确提供，原始 1254 图的 down/up/left/right 分别使用 X=635/635/600/665。

```sh
h3-character normalize-master examples/jade-traveler/masters/right.png \
  --root-x 665 --output examples/jade-traveler/prepared/right.png
```

生产 `character.yaml` 引用 `prepared/`，原始母版不覆盖。布局回执记录原图与新图摘要、缩放、偏移和实体轮廓；细微透明边噪声保留，不用它确定地面。提示词及种子是可追踪的输入，重新生成仍不保证相同像素。
