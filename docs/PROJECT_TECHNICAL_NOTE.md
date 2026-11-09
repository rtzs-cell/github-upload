# Radar Simulate 项目技术说明

## 摘要

Radar Simulate 是一个面向城市雷达传播与信号处理的 Sionna RT 工作台。系统把场景几何、雷达姿态、阵列参数、传播求解、路径分析和 FMCW 后处理组织在同一套实验方案中。本文档说明近期加入的多来源场景导入能力。系统现在可以导入 OpenStreetMap 建筑面、Overpass JSON、GeoJSON、自定义场景 JSON 以及 OBJ/PLY 模型，并将这些来源组合成可继续编辑的混合场景。

导入的地图建筑会被转换到以导入区域中心为原点的局部米制坐标。建筑高度优先读取 `height`，其次使用 `building:levels` 估计，缺少高度标签时使用 12 m 默认值。保存场景时，后端将参数化建筑写入 Sionna RT 场景 XML 和网格文件。导入文件和对象的来源信息保留在实验目录中，便于回查。

## 1. 项目目标

城市雷达传播仿真通常需要同时处理三类场景来源。

1. 规则参数化建筑用于快速构造可控的对照场景。
2. OpenStreetMap 或 GeoJSON 建筑面用于表达真实街区布局。
3. OBJ/PLY 模型和自定义场景 JSON 用于加入局部细节或已有建模结果。

项目的场景编辑器将三类来源统一为可编辑的建筑对象。实验方案保存后生成新的场景修订，已经完成的仿真结果继续引用提交时的旧修订。

## 2. 系统结构

### 2.1 后端

后端使用 FastAPI，主要模块如下。

- `services/radar_api/app/core/scene_imports.py` 负责 OSM XML、Overpass JSON 和 GeoJSON 的解析。
- `services/radar_api/app/api/experiments.py` 提供场景文件上传接口。
- `services/radar_api/app/core/two_building_scene.py` 负责场景配置校验、场景 XML 和 PLY 网格生成。
- `services/radar_api/app/workers/simulation_worker.py` 读取保存后的实验配置并提交 Sionna RT 仿真。

上传的原始场景文件保存到实验目录的 `scene/imports/` 下。解析结果以建筑对象列表返回给前端，只有用户保存实验方案后才会写入新的场景修订。

### 2.2 前端

前端使用 React、TypeScript、Three.js 和 React Three Fiber。

- `SceneGeometryEditor.tsx` 提供场景导入、建筑列表编辑、撤销重做和保存。
- `Scene3D.tsx` 显示建筑、雷达和传播路径，并支持选中对象后的三维变换。
- `client.ts` 封装场景导入 API。
- `radarConfig.ts` 将实验方案转换为雷达编辑器和三维场景所需的数据结构。

导入界面提供两种模式。

- 追加到当前场景。保留当前地面和建筑，导入对象加入同一方案并将场景标记为混合场景。
- 替换当前建筑。用导入文件中的建筑替换当前建筑列表，并将雷达观察点重新定位到导入建筑中心。

## 3. 地图场景导入

### 3.1 OSM XML

解析器读取 OSM 节点和带 `building` 或 `building:part` 标签的闭合 way。节点的经纬度通过局部等距近似投影到米制坐标：

[
x = (lambda-lambda_0) cos(phi_0) M_{lambda}, qquad
y = (phi-phi_0) M_{phi}
]

其中 ((phi_0,lambda_0)) 是导入区域中心，(M_{phi}) 和 (M_{lambda}) 分别取每纬度和每经度的近似米数。

建筑高度解析规则如下。

1. 读取 `height` 或 `building:height`。
2. 没有明确高度时读取 `building:levels`，按每层 3.2 m 估计。
3. 仍无高度信息时使用 12 m。

每个建筑对象保留来源类型、OSM way ID、源文件路径和有限的原始标签。建筑的原始面也保存在 `footprint_m` 中。

### 3.2 Overpass JSON 和 GeoJSON

Overpass JSON 支持 `elements` 中的节点、way 和 way geometry。GeoJSON 支持 FeatureCollection、Feature、Polygon 和 MultiPolygon。GeoJSON 的坐标按 WGS84 经纬度处理。

当前仿真场景以参数化建筑盒体表达导入对象。复杂曲线和带洞多边形使用外包围盒参与传播计算，原始外轮廓仍保留在对象元数据中。这一选择保证了导入对象可以继续使用现有的移动、缩放、旋转和场景 XML 生成链路。

## 4. API

场景导入接口如下。

```text
POST /api/experiments/{experiment_id}/scene-imports?filename=map.osm
Content-Type: application/octet-stream
```

目前限制单个场景文件最大 50 MB。成功响应包含：

- `source_type`
- `original_filename`
- `source_path`
- `origin`
- `object_count`
- `warnings`
- `buildings`

场景 JSON 和 OBJ/PLY 模型沿用原有接口。导入后的对象必须通过实验方案保存接口写入场景修订，才会参与后续仿真。

## 5. 验证

针对本次功能保留了关键测试。

- OSM XML 建筑面投影、建筑高度和来源 ID。
- GeoJSON 建筑属性读取。
- 场景导入 API、源文件保存和混合场景保存。
- 原有参数化场景创建、场景修订和 OBJ/PLY 模型导入。
- 前端 TypeScript 编译和 Vite 生产构建。
- `git diff --check` 和 Python 模块编译检查。

测试验证了导入链路和旧场景编辑链路。当前结果分析测试依赖项目中已有的示例结果目录，示例结果缺失时不会影响场景导入测试。

## 6. 使用流程

1. 创建或打开一个实验方案。
2. 进入“场景几何”。
3. 选择“追加到当前场景（混合）”或“替换当前建筑”。
4. 点击“导入 OSM / GeoJSON”并选择场景文件。
5. 检查建筑数量、坐标和高度。
6. 在三维视图或右侧字段中调整对象。
7. 点击“保存场景”生成新的场景修订。
8. 在“雷达参数”中确认雷达中心、观察点和距离范围。
9. 提交仿真任务。

## 7. 当前边界

当前版本面向建筑传播场景，重点覆盖闭合 building way、Overpass building way 和 GeoJSON 建筑面。OSM 关系型 multipolygon、道路表面、植被和地形尚未转化为独立的传播几何。复杂建筑仍按外包围盒参与仿真，因此需要精确外形时应使用 OBJ/PLY 模型。

导入坐标使用局部投影，适合单个街区或中小范围场景。大范围城市数据需要进一步加入分区、投影带和场景分块策略。

## 8. 后续研究方向

后续可以围绕以下问题扩展。

- 将 OSM multipolygon 关系转换为带洞的挤出网格。
- 将道路、地面材质和建筑材质映射到更细的 Sionna RT 材料集合。
- 对大范围地图采用分块加载和视野裁剪。
- 在独立场景数据上比较盒体近似和真实网格对传播路径、MPC 与 FMCW 结果的影响。
- 为导入场景建立统一的坐标、单位和数据版本记录。

本文档描述的是当前实现和已验证的工程能力，不把尚未完成的精确网格传播和大范围地图评测作为已完成结果。
