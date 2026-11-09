import { Line, OrbitControls, Text, TransformControls } from '@react-three/drei'
import { Canvas, useLoader, useThree } from '@react-three/fiber'
import type { ThreeEvent } from '@react-three/fiber'
import { Eye, EyeOff, Maximize, Move3D, Rotate3D, Route, ScanLine, Scaling, Sparkles, X } from 'lucide-react'
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { RadarDraftConfig, SceneObject, TopPath } from '../api/types'
import { boresightAzimuthDeg } from './radarConfig'

const materialColors: Record<string, string> = {
  glass: '#7fc4d7',
  brick: '#c77662',
  marble: '#c9cbd4',
  wood: '#b49a68',
  concrete: '#a9b6b8',
  metal: '#727d80',
}

function vec3(values: [number, number, number]) {
  return new THREE.Vector3(values[0], values[1], values[2])
}

type ViewBounds = {
  target: [number, number, number]
  camera: [number, number, number]
  gridSize: number
}

function CameraRig({ bounds, viewKey }: { bounds: ViewBounds; viewKey: string }) {
  const { camera } = useThree()
  useEffect(() => {
    camera.position.set(bounds.camera[0], bounds.camera[1], bounds.camera[2])
    camera.lookAt(bounds.target[0], bounds.target[1], bounds.target[2])
    camera.updateProjectionMatrix()
  }, [bounds, camera, viewKey])
  return null
}

function computeViewBounds(objects: SceneObject[], config: RadarDraftConfig): ViewBounds {
  const points: Array<[number, number, number]> = [
    [config.center_m[0], config.center_m[2], config.center_m[1]],
    [config.look_at_m[0], config.look_at_m[2], config.look_at_m[1]],
  ]
  for (const object of objects.filter((item) => item.object_id !== 'floor')) {
    points.push([object.bbox_min[0], object.bbox_min[2], object.bbox_min[1]])
    points.push([object.bbox_max[0], object.bbox_max[2], object.bbox_max[1]])
  }
  const min = [Infinity, Infinity, Infinity]
  const max = [-Infinity, -Infinity, -Infinity]
  for (const point of points) {
    for (let i = 0; i < 3; i += 1) {
      min[i] = Math.min(min[i], point[i])
      max[i] = Math.max(max[i], point[i])
    }
  }
  const target: [number, number, number] = [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ]
  const span = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 80)
  const distance = span * 1.15
  return {
    target,
    camera: [target[0] - distance * 0.52, target[1] + distance * 0.55, target[2] + distance * 0.62],
    gridSize: Math.max(220, span * 1.6),
  }
}

function computePathViewBounds(path: TopPath, fallback: ViewBounds): ViewBounds {
  if (path.polyline_m.length < 2) return fallback
  const points = path.polyline_m.map(([x, y, z]) => [x, z, y] as [number, number, number])
  const min = [Infinity, Infinity, Infinity]
  const max = [-Infinity, -Infinity, -Infinity]
  for (const point of points) {
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], point[axis])
      max[axis] = Math.max(max[axis], point[axis])
    }
  }
  const target: [number, number, number] = [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ]
  const span = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 18)
  const distance = span * 1.25
  return {
    target,
    camera: [target[0] - distance * 0.46, target[1] + distance * 0.62, target[2] + distance * 0.7],
    gridSize: Math.max(80, span * 2),
  }
}

function objectTransform(object: SceneObject) {
  const min = object.bbox_min
  const max = object.bbox_max
  const simSize = object.size_m ?? [max[0] - min[0], max[1] - min[1], max[2] - min[2]]
  const simCenter = object.center_m ?? object.bbox_center
  const size: [number, number, number] = [simSize[0], simSize[2], simSize[1]]
  const pos: [number, number, number] = [
    simCenter[0],
    simCenter[2],
    simCenter[1],
  ]
  return { size, pos, rotation: object.rotation_deg ?? [0, 0, 0] as [number, number, number] }
}

const coordinateSwap = new THREE.Matrix4().set(
  1, 0, 0, 0,
  0, 0, 1, 0,
  0, 1, 0, 0,
  0, 0, 0, 1,
)

function simulationQuaternion(rotationDeg: [number, number, number]) {
  const radians = rotationDeg.map((value) => value * Math.PI / 180) as [number, number, number]
  const simulation = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(radians[0], radians[1], radians[2], 'XYZ'))
  const converted = coordinateSwap.clone().multiply(simulation).multiply(coordinateSwap)
  return new THREE.Quaternion().setFromRotationMatrix(converted)
}

function simulationEulerDegrees(quaternion: THREE.Quaternion): [number, number, number] {
  const rendered = new THREE.Matrix4().makeRotationFromQuaternion(quaternion)
  const simulation = coordinateSwap.clone().multiply(rendered).multiply(coordinateSwap)
  const euler = new THREE.Euler().setFromRotationMatrix(simulation, 'XYZ')
  return [euler.x, euler.y, euler.z].map((value) => roundMeter(value * 180 / Math.PI)) as [number, number, number]
}

function modelPlacement(object: SceneObject) {
  const model = object.model!
  const sourceSize = model.source_bbox_max.map((value, index) => Math.max(value - model.source_bbox_min[index], 1e-9))
  const sourceCenter = model.source_bbox_max.map((value, index) => (value + model.source_bbox_min[index]) / 2)
  const target = object.size_m ?? [1, 1, 1]
  const simScale = target.map((value, index) => value / sourceSize[index])
  const scale: [number, number, number] = [simScale[0], simScale[2], simScale[1]]
  const position: [number, number, number] = [
    -sourceCenter[0] * scale[0],
    -sourceCenter[2] * scale[1],
    -sourceCenter[1] * scale[2],
  ]
  return { scale, position }
}

function convertGeometry(geometry: THREE.BufferGeometry) {
  const converted = geometry.clone()
  converted.applyMatrix4(coordinateSwap)
  converted.computeVertexNormals()
  return converted
}

function PlyModel({ object }: { object: SceneObject }) {
  const source = useLoader(PLYLoader, object.model!.preview_url)
  const geometry = useMemo(() => convertGeometry(source), [source])
  const { scale, position } = modelPlacement(object)
  return <mesh geometry={geometry} scale={scale} position={position}>
    <meshStandardMaterial color={materialColors[object.material] ?? '#b8c0c2'} roughness={0.72} metalness={object.material === 'metal' ? 0.72 : 0.08} side={THREE.DoubleSide} />
  </mesh>
}

function ObjModel({ object }: { object: SceneObject }) {
  const source = useLoader(OBJLoader, object.model!.preview_url)
  const model = useMemo(() => {
    const clone = source.clone(true)
    clone.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return
      child.geometry = convertGeometry(child.geometry)
      child.material = new THREE.MeshStandardMaterial({
        color: materialColors[object.material] ?? '#b8c0c2',
        roughness: 0.72,
        metalness: object.material === 'metal' ? 0.72 : 0.08,
        side: THREE.DoubleSide,
      })
    })
    return clone
  }, [object.material, source])
  const { scale, position } = modelPlacement(object)
  return <primitive object={model} scale={scale} position={position} />
}

function BuildingMesh({ object, selected, onSelect }: { object: SceneObject; selected: boolean; onSelect: () => void }) {
  const { size } = objectTransform(object)
  return <group onClick={(event) => { event.stopPropagation(); onSelect() }}>
    {object.geometry_kind === 'model' && object.model ? <Suspense fallback={<mesh><boxGeometry args={size} /><meshStandardMaterial color="#839699" wireframe /></mesh>}>
      {object.model.format === 'obj' ? <ObjModel object={object} /> : <PlyModel object={object} />}
    </Suspense> : <mesh>
      <boxGeometry args={size} />
      <meshStandardMaterial
        color={materialColors[object.material] ?? '#b8c0c2'}
        emissive={selected ? '#176b5a' : '#000000'}
        emissiveIntensity={selected ? 0.32 : 0}
        transparent
        opacity={selected ? 0.82 : 0.62}
      />
    </mesh>}
    {selected && <mesh>
      <boxGeometry args={size.map((value) => value + 0.35) as [number, number, number]} />
      <meshBasicMaterial color="#087a68" wireframe depthTest={false} />
    </mesh>}
  </group>
}

function EditableBuilding({ object, selected, editable, mode, onSelect, onTransform, onDraggingChange }: {
  object: SceneObject
  selected: boolean
  editable: boolean
  mode: 'translate' | 'rotate' | 'scale'
  onSelect: () => void
  onTransform: (centerM: [number, number, number], sizeM: [number, number, number], rotationDeg: [number, number, number]) => void
  onDraggingChange: (dragging: boolean) => void
}) {
  const group = useRef<THREE.Group>(null)
  const [transformTarget, setTransformTarget] = useState<THREE.Group | null>(null)
  const attachGroup = useCallback((value: THREE.Group | null) => {
    group.current = value
    setTransformTarget(value)
  }, [])
  const { size, pos, rotation } = objectTransform(object)
  useEffect(() => {
    if (!group.current) return
    group.current.position.set(...pos)
    group.current.quaternion.copy(simulationQuaternion(rotation))
    group.current.scale.set(1, 1, 1)
    group.current.updateMatrixWorld(true)
  }, [object.bbox_min, object.bbox_max, rotation])

  const commit = () => {
    onDraggingChange(false)
    const current = group.current
    if (!current) return
    const sizeM: [number, number, number] = [
      Math.max(0.1, roundMeter(size[0] * Math.abs(current.scale.x))),
      Math.max(0.1, roundMeter(size[2] * Math.abs(current.scale.z))),
      Math.max(0.1, roundMeter(size[1] * Math.abs(current.scale.y))),
    ]
    const centerM: [number, number, number] = [
      roundMeter(current.position.x),
      roundMeter(current.position.z),
      Math.max(roundMeter(current.position.y), roundMeter(sizeM[2] / 2)),
    ]
    current.scale.set(1, 1, 1)
    onTransform(centerM, sizeM, simulationEulerDegrees(current.quaternion))
  }

  const content = <group ref={attachGroup} position={pos}>
    <BuildingMesh object={object} selected={selected} onSelect={onSelect} />
  </group>
  if (!selected || !editable) return content
  return <>
    {content}
    {transformTarget && <TransformControls
      object={transformTarget}
      mode={mode}
      translationSnap={0.5}
      scaleSnap={0.05}
      rotationSnap={Math.PI / 36}
      size={0.82}
      onMouseDown={() => onDraggingChange(true)}
      onMouseUp={commit}
    />}
  </>
}

function roundMeter(value: number) {
  return Math.round(value * 10) / 10
}

function translateRadarOnGround(config: RadarDraftConfig, point: THREE.Vector3): RadarDraftConfig {
  const nextCenter: [number, number, number] = [
    roundMeter(point.x),
    roundMeter(point.z),
    config.center_m[2],
  ]
  const dx = nextCenter[0] - config.center_m[0]
  const dy = nextCenter[1] - config.center_m[1]
  const nextLookAt: [number, number, number] = [
    roundMeter(config.look_at_m[0] + dx),
    roundMeter(config.look_at_m[1] + dy),
    config.look_at_m[2],
  ]
  return {
    ...config,
    center_m: nextCenter,
    look_at_m: nextLookAt,
  }
}

function RadarGlyph({
  config,
  draggable,
  dragging,
  onDragStart,
}: {
  config: RadarDraftConfig
  draggable: boolean
  dragging: boolean
  onDragStart: (event: ThreeEvent<PointerEvent>) => void
}) {
  const center = vec3(config.center_m)
  const look = vec3(config.look_at_m)
  const dir = look.clone().sub(center).normalize()
  const side = new THREE.Vector3(-dir.z, 0, dir.x).normalize()
  const baseline = config.tx_rx_baseline_m || 0.1
  const tx = center.clone().add(side.clone().multiplyScalar(-baseline / 2))
  const rx = center.clone().add(side.clone().multiplyScalar(baseline / 2))
  const arrowEnd = center.clone().add(dir.clone().multiplyScalar(Math.min(config.rmax_m, 40)))
  const az = boresightAzimuthDeg(config)
  const handlePointerOver = () => {
    if (draggable) document.body.style.cursor = dragging ? 'grabbing' : 'grab'
  }
  const handlePointerOut = () => {
    if (!dragging) document.body.style.cursor = ''
  }
  return (
    <group
      onPointerDown={draggable ? onDragStart : undefined}
      onPointerOver={handlePointerOver}
      onPointerOut={handlePointerOut}
    >
      <mesh position={[tx.x, tx.z, tx.y]}>
        <sphereGeometry args={[0.9, 16, 16]} />
        <meshStandardMaterial color="#0d6d5f" />
      </mesh>
      <mesh position={[rx.x, rx.z, rx.y]}>
        <boxGeometry args={[1.4, 1.4, 1.4]} />
        <meshStandardMaterial color="#f3b33d" />
      </mesh>
      <Line
        points={[
          [center.x, center.z, center.y],
          [arrowEnd.x, arrowEnd.z, arrowEnd.y],
        ]}
        color="#68858a"
        lineWidth={2}
        dashed
        dashSize={1.2}
        gapSize={0.7}
      />
      <mesh position={[rx.x, rx.z, rx.y]} rotation={[0, (-az * Math.PI) / 180, 0]}>
        <planeGeometry args={[5.2, 5.2]} />
        <meshStandardMaterial color="#f3b33d" transparent opacity={0.28} side={THREE.DoubleSide} />
      </mesh>
      <Text position={[center.x, center.z + 2.8, center.y]} fontSize={2} color="#17333a" anchorX="center">
        雷达
      </Text>
    </group>
  )
}

function RadarDragPlane({
  bounds,
  config,
  onChange,
  onStop,
}: {
  bounds: ViewBounds
  config: RadarDraftConfig
  onChange: (next: RadarDraftConfig) => void
  onStop: () => void
}) {
  const planeSize = Math.max(bounds.gridSize * 2, 1200)
  const altitude = config.center_m[2]
  const handleMove = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation()
    onChange(translateRadarOnGround(config, event.point))
  }
  const handleStop = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation()
    onStop()
  }
  return (
    <mesh
      position={[bounds.target[0], altitude, bounds.target[2]]}
      rotation={[-Math.PI / 2, 0, 0]}
      onPointerMove={handleMove}
      onPointerUp={handleStop}
      onPointerCancel={handleStop}
    >
      <planeGeometry args={[planeSize, planeSize]} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} />
    </mesh>
  )
}

function FovFrustum({ config }: { config: RadarDraftConfig }) {
  const points = useMemo(() => {
    const center = vec3(config.center_m)
    const azCenter = (boresightAzimuthDeg(config) * Math.PI) / 180
    const azHalf = (config.az_width_deg * Math.PI) / 360
    const elMin = (config.el_min_deg * Math.PI) / 180
    const elMax = (config.el_max_deg * Math.PI) / 180
    const r = Math.min(config.rmax_m, 1000)
    const corners: THREE.Vector3[] = []
    for (const az of [azCenter - azHalf, azCenter + azHalf]) {
      for (const el of [elMin, elMax]) {
        corners.push(
          center.clone().add(
            new THREE.Vector3(
              r * Math.cos(el) * Math.cos(az),
              r * Math.cos(el) * Math.sin(az),
              r * Math.sin(el),
            ),
          ),
        )
      }
    }
    return { center, corners }
  }, [config])
  const c = [points.center.x, points.center.z, points.center.y] as [number, number, number]
  const mapped = points.corners.map((p) => [p.x, p.z, p.y] as [number, number, number])
  const edges: Array<[number, number, number][]> = [
    [c, mapped[0]],
    [c, mapped[1]],
    [c, mapped[2]],
    [c, mapped[3]],
    [mapped[0], mapped[1]],
    [mapped[0], mapped[2]],
    [mapped[3], mapped[1]],
    [mapped[3], mapped[2]],
  ]
  return (
    <group>
      {edges.map((edge, idx) => (
        <Line key={idx} points={edge} color="#17a6a6" transparent opacity={0.7} lineWidth={2} />
      ))}
    </group>
  )
}

function PathLines({
  paths,
  showInteractionMarkers,
  onSelect,
}: {
  paths: TopPath[]
  showInteractionMarkers: boolean
  onSelect?: (pathId: number) => void
}) {
  return (
    <group>
      {paths.flatMap((path) => {
        const points = path.polyline_m.map(([x, y, z]) => [x, z, y] as [number, number, number])
        const lineWidth = Math.max(1, Math.min(4, 1 + Math.log10(path.energy / 1e-13)))
        return [
          <Line
            key={`${path.path_id}-highlight`}
            points={points}
            color="#f3b33d"
            transparent
            opacity={0.96}
            lineWidth={lineWidth + 5.2}
            depthTest={false}
            renderOrder={20}
          />,
          ...points.slice(0, -1).map((point, idx) => {
            const isReturnSegment = idx === points.length - 2
            const isIntermediateSegment = idx > 0 && !isReturnSegment
            const color = isReturnSegment ? '#b4372f' : isIntermediateSegment ? '#7b4ab7' : '#0d6d5f'
            return (
              <Line
                key={`${path.path_id}-segment-${idx}`}
                points={[point, points[idx + 1]]}
                color={color}
                transparent
                opacity={1}
                lineWidth={isReturnSegment ? lineWidth + 1.2 : lineWidth + 0.4}
                depthTest={false}
                renderOrder={21}
                onClick={(event) => {
                  event.stopPropagation()
                  onSelect?.(path.path_id)
                }}
              />
            )
          }),
        ]
      })}
      {showInteractionMarkers && paths.flatMap((path) =>
        path.interactions.map((interaction, idx) => (
          <mesh
            key={`${path.path_id}-${idx}`}
            position={[
              interaction.position_m[0],
              interaction.position_m[2],
              interaction.position_m[1],
            ]}
            onClick={(event) => {
              event.stopPropagation()
              onSelect?.(path.path_id)
            }}
          >
            <sphereGeometry args={[interaction.type === 'diffuse' ? 1.25 : 1.05, 14, 14]} />
            <meshStandardMaterial
              color={interaction.type === 'diffuse' ? '#d9822b' : '#1f78b4'}
              emissive={interaction.type === 'diffuse' ? '#4a2300' : '#062642'}
              emissiveIntensity={0.2}
              transparent
              opacity={0.96}
              depthTest={false}
            />
          </mesh>
        )),
      )}
    </group>
  )
}

export function Scene3D({
  objects,
  paths,
  config,
  viewKey,
  onConfigChange,
  selectedPathId = null,
  onPathSelect,
  selectedObjectId = null,
  editableObjects = false,
  onObjectSelect,
  onObjectTransform,
}: {
  objects: SceneObject[]
  paths: TopPath[]
  config: RadarDraftConfig
  viewKey?: string
  onConfigChange?: (next: RadarDraftConfig) => void
  selectedPathId?: number | null
  onPathSelect?: (pathId: number) => void
  selectedObjectId?: string | null
  editableObjects?: boolean
  onObjectSelect?: (objectId: string | null) => void
  onObjectTransform?: (objectId: string, centerM: [number, number, number], sizeM: [number, number, number], rotationDeg: [number, number, number]) => void
}) {
  const cameraViewKey = viewKey ?? config.scene_id
  const [viewRevision, setViewRevision] = useState(0)
  const boundsCache = useRef<{ key: string; value: ViewBounds } | null>(null)
  const sceneReadiness = objects.length > 0 ? 'ready' : 'loading'
  const boundsKey = `${cameraViewKey}-${viewRevision}-${sceneReadiness}`
  if (!boundsCache.current || boundsCache.current.key !== boundsKey) {
    boundsCache.current = { key: boundsKey, value: computeViewBounds(objects, config) }
  }
  const bounds = boundsCache.current.value
  const selectedPath = useMemo(() => paths.find((path) => path.path_id === selectedPathId) ?? null, [paths, selectedPathId])
  const [draggingRadar, setDraggingRadar] = useState(false)
  const [showPaths, setShowPaths] = useState(true)
  const [showInteractions, setShowInteractions] = useState(true)
  const [showFov, setShowFov] = useState(false)
  const [focusSelectedPath, setFocusSelectedPath] = useState(false)
  const [objectTransformMode, setObjectTransformMode] = useState<'translate' | 'rotate' | 'scale'>('translate')
  const [transformingObject, setTransformingObject] = useState(false)
  const draggable = Boolean(onConfigChange)
  const viewBounds = useMemo(
    () => focusSelectedPath && selectedPath ? computePathViewBounds(selectedPath, bounds) : bounds,
    [bounds, focusSelectedPath, selectedPath],
  )

  useEffect(() => setFocusSelectedPath(selectedPathId !== null), [cameraViewKey, selectedPathId])

  useEffect(() => {
    if (!draggingRadar) {
      document.body.style.cursor = ''
      return undefined
    }
    document.body.style.cursor = 'grabbing'
    const stop = () => setDraggingRadar(false)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
      document.body.style.cursor = ''
    }
  }, [draggingRadar])

  const startRadarDrag = (event: ThreeEvent<PointerEvent>) => {
    if (!onConfigChange) return
    event.stopPropagation()
    setDraggingRadar(true)
  }

  const updateRadarPosition = (next: RadarDraftConfig) => {
    onConfigChange?.(next)
  }

  return (
    <div className={`scene3d-shell ${draggingRadar ? 'dragging-radar' : ''}`}>
      <Canvas camera={{ position: [105, 78, 120], fov: 48 }} gl={{ antialias: true }} onPointerMissed={() => onObjectSelect?.(null)}>
        <CameraRig bounds={viewBounds} viewKey={`${boundsKey}-${focusSelectedPath ? selectedPathId : 'scene'}`} />
        <color attach="background" args={['#eef3f2']} />
        <ambientLight intensity={0.8} />
        <directionalLight position={[30, 80, 40]} intensity={1.1} />
        <gridHelper args={[viewBounds.gridSize, 44, '#9db0b4', '#d3dddf']} position={[viewBounds.target[0], -0.05, viewBounds.target[2]]} />
        {objects.filter((obj) => obj.object_id !== 'floor').map((obj) => (
          <EditableBuilding
            key={obj.object_id}
            object={obj}
            selected={selectedObjectId === obj.object_id}
            editable={editableObjects}
            mode={objectTransformMode}
            onSelect={() => onObjectSelect?.(obj.object_id)}
            onDraggingChange={setTransformingObject}
            onTransform={(centerM, sizeM, rotationDeg) => onObjectTransform?.(obj.object_id, centerM, sizeM, rotationDeg)}
          />
        ))}
        <RadarGlyph config={config} draggable={draggable} dragging={draggingRadar} onDragStart={startRadarDrag} />
        {draggingRadar && onConfigChange && (
          <RadarDragPlane
            bounds={bounds}
            config={config}
            onChange={updateRadarPosition}
            onStop={() => setDraggingRadar(false)}
          />
        )}
        {showFov && <FovFrustum config={config} />}
        {showPaths && (
          <PathLines
            paths={paths}
            showInteractionMarkers={showInteractions}
            onSelect={onPathSelect}
          />
        )}
        <OrbitControls makeDefault target={viewBounds.target} enabled={!draggingRadar && !transformingObject} />
      </Canvas>
      <div className="scene-toolbar" aria-label="三维场景图层">
        <button type="button" className={showPaths ? 'active' : ''} onClick={() => setShowPaths((value) => !value)} title="显示或隐藏传播路径">
          {showPaths ? <Eye size={14} /> : <EyeOff size={14} />}
          <span>{selectedPathId === null ? '未选路径' : `路径 #${selectedPathId}`}</span>
        </button>
        <button type="button" disabled={selectedPathId === null} className={showInteractions ? 'active' : ''} onClick={() => setShowInteractions((value) => !value)} title="显示或隐藏当前路径交互点">
          <Sparkles size={14} />
          <span>交互点</span>
        </button>
        <button type="button" className={showFov ? 'active' : ''} onClick={() => setShowFov((value) => !value)} title="显示或隐藏分析范围边界">
          <ScanLine size={14} />
          <span>分析范围</span>
        </button>
        <button type="button" onClick={() => setViewRevision((value) => value + 1)} title="重新适应完整场景"><Maximize size={14} /><span>适应场景</span></button>
        {editableObjects && selectedObjectId && <>
          <button type="button" className={objectTransformMode === 'translate' ? 'active' : ''} onClick={() => setObjectTransformMode('translate')} title="移动选中建筑">
            <Move3D size={14} /><span>移动</span>
          </button>
          <button type="button" className={objectTransformMode === 'scale' ? 'active' : ''} onClick={() => setObjectTransformMode('scale')} title="缩放建筑：红轴调整 X，蓝轴调整 Y，绿轴调整 Z 高度；中心方块整体缩放">
            <Scaling size={14} /><span>缩放</span>
          </button>
          <button type="button" className={objectTransformMode === 'rotate' ? 'active' : ''} onClick={() => setObjectTransformMode('rotate')} title="旋转选中对象">
            <Rotate3D size={14} /><span>旋转</span>
          </button>
          <button type="button" onClick={() => onObjectSelect?.(null)} title="取消选择"><X size={14} /></button>
        </>}
        {selectedPathId !== null && (
          <button
            type="button"
            className={`selected-path-chip ${focusSelectedPath ? 'active' : ''}`}
            onClick={() => setFocusSelectedPath((value) => !value)}
            title={focusSelectedPath ? '恢复全场景视图' : '聚焦选中路径'}
          >
            <Route size={13} />#{selectedPathId}
          </button>
        )}
      </div>
      {selectedObjectId && <div className="selected-object-label">{objects.find((item) => item.object_id === selectedObjectId)?.display_name ?? selectedObjectId}</div>}
      <div className="scene3d-legend" aria-label="三维场景图例">
        <span className="legend-dot radar">雷达位置</span>
        <span className="legend-line boresight">主视轴</span>
        <span className="legend-line transmit">发射段</span>
        <span className="legend-line echo">回波段</span>
        <span className="legend-dot specular">镜面反射点</span>
        <span className="legend-dot diffuse">漫反射/散射点</span>
      </div>
    </div>
  )
}
