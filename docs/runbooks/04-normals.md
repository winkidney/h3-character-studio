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

先逐帧标注可见脸部与命名银饰像素，绑定选帧来源 SHA256，经视觉审查后保存到 `runs/right-reviewed-materials`。下面命令依赖该目录；提案不能直接用于最终法线。

给首帧和其他关键姿态画实际几何。各关键姿态保持 shape ID、kind、点数及顺序一致；不能共用银饰少女旧坐标。遮挡拓扑有变化时，使用逐帧编辑，不靠插值伪装。

```sh
h3-character normals runs/right-001-selected/pixel-256 \
  --geometry examples/jade-traveler/geometry/right.yaml --materials runs/right-reviewed-materials --output runs/right-001-normals
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
  --materials runs/right-reviewed-materials --output runs/right-001-normals-v2
```

## 修订

逐帧复核全部动作，重点检查马尾根部和尾端、裙边与腿、腕环与手、腰链与皮包、前后脸遮挡及鞋交叉。新角色的银饰应按实际材质选择，玉坠和衣料刺绣不填入金属蒙版。

几何修订：复制已有 editable 目录到单独编辑版本，修改对应 `geometry.json`，用新输出目录重建。

```sh
h3-character normals runs/right-001-selected/pixel-256 --geometry examples/jade-traveler/geometry/right.yaml \
  --edits runs/right-001-edits --materials runs/right-reviewed-materials --output runs/right-002-normals
```

手绘向量层修订：复制 editable 后编辑各 shape PNG，保持其 Alpha／覆盖范围，RGB 按 `(normal+1)/2` 编码。不要给法线图套调色板。

```sh
h3-character normals runs/right-001-selected/pixel-256 --geometry examples/jade-traveler/geometry/right.yaml \
  --painted-layers runs/right-001-painted --materials runs/right-reviewed-materials --output runs/right-003-normals
```

修订输出使用新目录。合成重新归一化向量，保留原颜色文件与时序。蒙版由 `--materials` 中逐帧已审查的精确像素归属决定，geometry 运输及颜色选择仅提供提案。

## 验收

核对颜色摘要、全部帧时长、Alpha、图集留边／切片、单位向量、金属材质范围、全部相邻过渡和循环接缝。validation 中的光流对齐角度和 clay 动画是审查提示，不能自动认定光照稳定。

法线和材质纹理使用线性数据、最近邻采样、关闭 mipmap、禁止 sRGB 颜色转换。最后进入真实 Godot GPU 画面，用灰材质／原颜色、法线开关、扫光与金属高光开关分别检查；只有实际画面能证明受光和遮挡正确。

## 精细重绘与来源校验

本次青绿少女从粗略形体到银饰少女细度的修订见[独立topic](../topics/clothing-normals.md)。不把108张输出、单位向量正确或Alpha匹配当作衣褶已经画对。

`surface_region`将可见语义区域与椭球自身范围分开。`pixel_region`限定细小饰品的精确整数像素，仅用于明确逐帧geometry编辑；不能自动运输固定像素名单。体积插值包含半径、坡度、朝向、覆盖和归一化面方向。需要拓扑变化时用 `--edits`；`--painted-layers`读取每帧geometry和向量层后重新归一化。RGBA8再归一化可能产生一级量化差异，应验证向量角度和精确Alpha，不要求重编码字节完全相同。

```sh
python examples/jade-traveler/redraw_clothing.py runs/right-001-selected/pixel-256 runs/right-001-normals-v2 --direction right --output runs/right-precision-redraw-v6
h3-character normals runs/right-001-selected/pixel-256 --geometry runs/right-precision-redraw-v6/geometry.yaml --edits runs/right-precision-redraw-v6/edits --materials runs/right-reviewed-materials --output runs/right-001-normals-v6
python examples/jade-traveler/check_precision.py runs/right-001-selected/pixel-256 runs/right-001-normals-v6 --output output/right-precision.json
```

该例的六姿态坐标针对已选青绿少女的27帧，需要新角色自己的标注，不能直接套用到其他角色。工具保留全部逐帧形体、局部修正和向量层。`fallback_pixels`单独报告平面兜底；有兜底时完整形体覆盖标志为false。颜色、Alpha、时序和脚底不变，金属区域允许随审查后的实际饰品修正。


## 局部表面层次修订v7

用户要求不同部位之间的受光区别更清楚，单块区域不圆鼓。本轮保留v6语义覆盖，降低大体积曲率，再为袖面、手面、衣褶与发束分别绘制小幅表面朝向。使用已有精细包生成独立可编辑候选：

```sh
python examples/jade-traveler/refine_volume.py output/jade-traveler-precision-v6 runs/jade-local-volumes-v7
```

每方向保留每帧geometry、surface-orientations与独立向量PNG，使用painted_layers重组。不要仅用geometry重建，否则部位朝向修订会丢失。颜色与金属覆盖保持原样；金属向量重编码最大角误差限定1度。四方向循环接缝与材料内部时序规则继续检查。取消头发／衣物整体法线倍率增强，避免把整块披肩、裙面或头发鼓成错误圆体。

语义响应图集为可选shader配套，不代替上述法线绘制：

```sh
python examples/jade-traveler/build_material_response.py output/jade-traveler-local-volumes-v7 output/jade-material-response
```

它的R／G／B分别是头发、衣物与腰饰银。腰饰区必须与最终金属蒙版相交，背面没有可见腰饰时允许为零。图集与角色方向、atlas_region同步绑定，线性、无损、最近邻、禁用mipmap。

## 本次外部块修复：逐帧材料和脸部归属

参见 [独立讲解 topic](../topics/foreground-and-material-ownership.md)。`normals` 现在通过 `--materials <目录>` 接收 `00000.json` 等源 SHA256 绑定的逐帧标注。含银饰或脸部表面的绘制不再接受未审查的几何运输结果。

先运行 `examples/jade-traveler/prepare_reviewed_surfaces.py` 生成提案与可视化；逐帧检查后再设置 `agent-reviewed` 或 `user-approved` 并填写审查者。提案不能直接改名当最终标注。标注包括 `regions`（命名饰品）、`protected_regions`（皮肤等禁止金属覆盖的像素）、`surface_regions`（脸部等身体表面）。不要用肤色凸包扩大脸部，不再生成独立 `nose-volume` 或按中性色自动认可银饰岛。

这次重新抠图改变了最终颜色 PNG 的 alpha 和边缘颜色，但 H3 原始动画保持不变。旧稀疏法线层必须重绘覆盖范围，并使用相同源帧指纹；不得复用过期层或过期蒙版。

## 讲解时的用途与来源标注

颜色图负责服装、肤色和纹理，本案例由 ImageGen 母版、H3 动画生成与 ToonOut 前景提取形成。法线图存储线性表面方向，用于动态明暗与体积，本案例由语义几何重绘、光流运输和逐帧修正形成；ImageGen 的灰材质图只是辅助体积参考。金属蒙版限定银饰镜面反射，白色金属、黑色非金属，本案例由源指纹绑定的逐帧像素归属标注形成。蒙版不是新的颜色贴图，也不能覆盖皮肤等非金属表面。

展示这三类图时，在各图片下分别写用途和实际工作流／模型来源，不笼统声称三者均由生图模型直接输出。概念图和四方向母版使用生图模型，屏幕标注“需要 GPT Image 或本地 Qwen 2.1 等生图模型”；实际生成来源仍按回执记录。
