# 法线自动绘制与材质蒙版

这一步接受已选定的 256×256 颜色序列。法线是向量，不是明暗照片。不要对颜色做 Sobel、亮度转高度、调色板映射或抖动；银色衣边与皮肤亮部都不能仅因“亮”就变成金属。

## 关键姿态与形体参考

每方向选择首帧、步态四分之一／二分之一／四分之三、末帧及待机帧。保留颜色联系图，先检查可见脸、双马尾、披肩、手臂、裙褶、包和鞋子的形体。需要辅助图时，用 ImageGen 制作灰材质体积参考：

```text
Use these exact ordered color poses of the same twin-ponytail traveler as reference.
Show a six-pose clay volume study with the same camera, silhouette and pose order.
Separate face/head volume, two unbraided ponytails and their roots, capelet folds,
sleeve cylinders, hip-driven skirt pleats, leather satchel, boots and metal ornaments.
Keep actual occlusion and garment attachment; back views must not show an invisible face.
Neutral gray clay, a readable directional light, no new costume or pose.
This is a form-study guide, not runtime normal-map pixel data.
```

辅助图只用于理解体积，不能裁成实际法线，也不把其表面颜色当向量编码。

## 标注与自动绘制

为每方向编写 geometry YAML。`examples/geometry.template.yaml` 只展示语法，其坐标不是新角色的已验收标注。坐标使用最终 256 图像的像素，X 向右、图像 Y 向下。关键帧编号使用选帧后的索引。

- ellipsoid 为脸、头发、披肩、胸廓、包等体积；ellipse 是中心与水平／竖直半径。
- tube 沿折线绘制马尾发束、手臂、鞋腿或饰品连接，半径和曲面方向独立于颜色。
- plane 用 polygon 描述衣料遮挡或明确平面。单元法线使用 X 向右、Y 向上、Z 向观察者。
- shape 顺序是从后向前的遮挡顺序，后绘制覆盖前者。clip_polygon 限制实际可见区；palette_colors 仅帮助限制某种材质，不生成坡度。metallic 标记金属部位。

给首帧和其他关键姿态画实际几何。各关键姿态保持 shape ID、kind、点数及顺序一致；不能共用银饰少女旧坐标。遮挡拓扑有变化时，使用逐帧编辑，不靠插值伪装。

```sh
h3-character normals runs/right-001-selected/pixel-256 \
  --geometry examples/jade-traveler/geometry/right.yaml --output runs/right-001-normals
h3-character verify-normals runs/right-001-selected/pixel-256 runs/right-001-normals
```

工具计算前后向 Farneback 光流，只将 RGB 当运动特征。它在相邻人工关键姿态之间双向传播几何，包含末帧回首帧，再解析绘制法线。颜色 Alpha 严格控制最终轮廓。材质蒙版白为金属、黑为其他材质，Alpha 同样匹配颜色。

输出包括逐帧法线、逐帧金属蒙版、配对图集、原精度运动的压缩副本、每帧 geometry JSON、语义 labels、每个 shape 的独立法线 PNG，以及 clay 动画。未标注区域使用平法线并明确统计；覆盖不足不视为完成美术。

本次青绿少女使用 `author_geometry.py` 记录各方向首帧语义体积，自动运输为五个可编辑锚点。五个锚点来自首帧运输，不是五次独立手绘。`cloth-base` 为未细分衣料提供平法线，因此 labels 全覆盖只证明每个像素有归属，不能证明体积细节都已完成。右向形体辅助图保存在 `geometry/references/`。

靴子在部分交叉步姿中出现运输偏离，使用 `correct_boots.py` 在逐帧标注的下肢区域重新计算可见轴线和脚部体积。皮革色组只用于限制材质，几何来自轮廓坐标。分区属于屏幕左右，不冒充遮挡时的解剖腿身份。所有修正保存为逐帧 geometry JSON，再用 `--edits` 重建到新目录。低分辨率关节交叉仍需查看完整动画和游戏扫光。

```sh
python examples/jade-traveler/author_geometry.py runs/right-001-selected/pixel-256 \
  --direction right --output examples/jade-traveler/geometry/right.yaml
python examples/jade-traveler/correct_boots.py runs/right-001-selected/pixel-256 \
  runs/right-001-normals/editable --output runs/right-boot-edits
h3-character normals runs/right-001-selected/pixel-256 \
  --geometry examples/jade-traveler/geometry/right.yaml --edits runs/right-boot-edits \
  --output runs/right-001-normals-v2
```

## 修订

逐帧复核全部动作，重点检查马尾根部和尾端、裙边与腿、腕环与手、腰链与皮包、前后脸遮挡及鞋交叉。新角色的银饰应按实际材质选择，玉坠和衣料刺绣不填入金属蒙版。

几何修订：复制已有 editable 目录到单独编辑版本，修改对应 `geometry.json`，用新输出目录重建。

```sh
h3-character normals runs/right-001-selected/pixel-256 --geometry examples/jade-traveler/geometry/right.yaml \
  --edits runs/right-001-edits --output runs/right-002-normals
```

手绘向量层修订：复制 editable 后编辑各 shape PNG，保持其 Alpha／覆盖范围，RGB 按 `(normal+1)/2` 编码。不要给法线图套调色板。

```sh
h3-character normals runs/right-001-selected/pixel-256 --geometry examples/jade-traveler/geometry/right.yaml \
  --painted-layers runs/right-001-painted --output runs/right-003-normals
```

修订输出使用新目录。合成重新归一化向量，保留原颜色文件与时序。蒙版随 geometry 的 metallic、clip_polygon 与 palette_colors 更新。

## 验收

核对颜色摘要、全部帧时长、Alpha、图集留边／切片、单位向量、金属材质范围、全部相邻过渡和循环接缝。validation 中的光流对齐角度和 clay 动画是审查提示，不能自动认定光照稳定。

法线和材质纹理使用线性数据、最近邻采样、关闭 mipmap、禁止 sRGB 颜色转换。最后进入真实 Godot GPU 画面，用灰材质／原颜色、法线开关、扫光与金属高光开关分别检查；只有实际画面能证明受光和遮挡正确。
