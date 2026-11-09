# 场景编辑器架构与扩展约束

本文说明参数化场景编辑器的数据边界。新增几何能力时应保持这些约束，避免三维预览、表单配置和 Sionna 场景文件出现三套互不一致的状态。

## 1. 单一编辑状态

实验方案加载后，`App.tsx` 创建一份 `sceneEditConfig`。以下操作只修改这一份配置：

- 右侧中心坐标和长宽高输入；
- 新增、复制、删除建筑；
- 材质修改；
- Three.js 移动和缩放操作轴；
- 撤销、重做和恢复已保存版本。

`SceneGeometryEditor` 是受控表单，`Scene3D` 是受控三维视图。两个组件不能再保存独立的建筑配置副本。

## 2. 对象身份

每个建筑包含两个名称：

- `id`：稳定内部标识，仅用于网格文件、Sionna 对象和前后端关联；
- `name`：用户可修改的显示名称。

重命名不能改变 `id`。复制建筑时必须生成新的唯一 `id`。三维选择、列表高亮和变换提交均使用 `id`，界面文本使用 `name`。

## 3. 坐标约定

配置和 Sionna 使用 `(X, Y, Z)`，其中 Z 为高度。Three.js 场景使用 `(X, Z, Y)` 映射：

```text
Sionna X -> Three X
Sionna Y -> Three Z
Sionna Z -> Three Y
```

所有位置和尺寸转换必须集中在三维对象适配函数中。不得在事件处理器中引入另一套轴约定。

## 4. 变换提交

操作轴拖动期间只更新 Three.js 目标对象，结束拖动时一次性提交：

1. 将世界位置转换回 Sionna 坐标；
2. 将 Group 缩放转换为建筑长宽高；
3. 应用最小尺寸与地面约束；
4. 写入 `sceneEditConfig`；
5. 生成一条撤销记录；
6. 重新生成预览对象。

OrbitControls 在操作轴拖动期间必须禁用，防止相机与建筑同时移动。

## 5. 保存与结果不可变性

未保存编辑只存在于浏览器。保存调用 `PUT /api/experiments/{id}`，后端必须生成：

```text
scene/revisions/<revision-id>/scene.xml
scene/revisions/<revision-id>/meshes/*.ply
```

禁止覆盖历史修订。仿真结果继续引用任务提交时的绝对场景路径，结果名称和方案名称也不能用于物理目录寻址。

## 6. 扩展新几何类型

当前编辑器支持轴对齐盒体。以后增加旋转建筑、圆柱、地形或导入网格时，应新增统一的几何适配层，并保持以下接口：

```text
config geometry -> preview object
config geometry -> PLY/XML asset
Three transform -> config geometry
config geometry -> validation and bounding box
```

不要在 `Scene3D.tsx`、表单和 XML 写出器中分别硬编码同一种几何。新类型必须同时提供后端验证、资产生成、预览选择、变换提交和修订测试。

## 7. 验证矩阵

每次扩展至少验证：

- 表单选择与画布选择双向同步；
- 移动和尺寸修改同步到表单；
- 撤销、重做和恢复已保存版本；
- 保存后生成新修订，旧 XML 保持不变；
- Sionna `load_scene(..., merge_shapes=False)` 保留对象数量和材质；
- 桌面画布非空且操作轴位于选中对象中心；
- 390 px 窄屏无横向溢出；
- 已完成结果保持只读。
