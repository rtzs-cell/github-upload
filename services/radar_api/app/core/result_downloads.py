from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


ARTIFACTS: dict[str, dict[str, str]] = {
    "config": {"relative_path": "config.yaml", "label": "仿真参数", "category": "config", "description": "本次仿真使用的完整参数"},
    "metadata": {"relative_path": "metadata.json", "label": "环境与场景信息", "category": "config", "description": "软件版本、计算设备、场景和阵列信息"},
    "metrics": {"relative_path": "metrics.json", "label": "指标摘要", "category": "analysis", "description": "路径、波束和 FMCW 摘要"},
    "cir": {"relative_path": "cir.npz", "label": "复数信道冲激响应（CIR）", "category": "raw", "description": "每个收发阵元对和每条路径的复数信道系数；通常是最大文件"},
    "cir_noiseless": {"relative_path": "cir_noiseless.npz", "label": "无噪声复数CIR", "category": "raw", "description": "启用CIR噪声时保留的无噪声复数信道冲激响应"},
    "paths_raw": {"relative_path": "paths_summary.npz", "label": "传播路径数组", "category": "raw", "description": "时延、角度、交互对象和路径顶点数组"},
    "paths_per_element": {"relative_path": "paths_per_element.npz", "label": "逐阵元传播路径数组", "category": "raw", "description": "真实阵列模式下每个收发阵元对的完整时延、角度、交互对象和路径顶点"},
    "radar_observation": {"relative_path": "radar_observation.npz", "label": "雷达观测数组", "category": "raw", "description": "波束后路径功率与距离角谱数组"},
    "paths_csv": {"relative_path": "analysis/paths.csv", "label": "完整路径表 CSV", "category": "table", "description": "逐路径距离、角度、能量和对象"},
    "path_gate_csv": {"relative_path": "analysis/analysis_gate_mpc.csv", "label": "分析范围内传播路径表", "category": "table", "description": "按方位、俯仰和距离范围筛选后的逐路径数据"},
    "mpc_summary": {"relative_path": "analysis/analysis_gate_mpc_summary.json", "label": "MPC 全景参数", "category": "analysis", "description": "到达角投影、等效接收孔径和归一化参数"},
    "mpc_panorama_array": {"relative_path": "analysis/mpc_panorama.npz", "label": "MPC 全景数值数组", "category": "analysis", "description": "到达角全景的未归一化 dB 数组和归一化矩阵"},
    "mpc_panorama_png": {"relative_path": "figures/mpc_panorama.png", "label": "MPC 到达角全景图", "category": "analysis", "description": "360°×180° 到达角等距柱状功率图"},
    "mpc_view_front": {"relative_path": "figures/mpc_view_front.png", "label": "MPC 前视图", "category": "analysis", "description": "90° 透视裁切"},
    "mpc_view_right": {"relative_path": "figures/mpc_view_right.png", "label": "MPC 右视图", "category": "analysis", "description": "90° 透视裁切"},
    "mpc_view_back": {"relative_path": "figures/mpc_view_back.png", "label": "MPC 后视图", "category": "analysis", "description": "90° 透视裁切"},
    "mpc_view_left": {"relative_path": "figures/mpc_view_left.png", "label": "MPC 左视图", "category": "analysis", "description": "90° 透视裁切"},
    "beamforming": {"relative_path": "analysis/beamformed_observation.npz", "label": "波束形成结果", "category": "analysis", "description": "发射与接收阵列加权后的相干路径系数和功率"},
    "fmcw": {"relative_path": "analysis/fmcw_range_doppler.npz", "label": "FMCW 距离-多普勒", "category": "analysis", "description": "距离-速度功率、CFAR 门限和检测掩码"},
    "fmcw_summary": {"relative_path": "analysis/fmcw_summary.json", "label": "FMCW 摘要", "category": "analysis", "description": "分辨率、噪声、覆盖率和检测结果"},
    "tx_element_pattern": {"relative_path": "analysis/tx_element_pattern.npz", "label": "Tx 单元因子", "category": "analysis", "description": "单个发射阵元方向图增益网格及原始自定义配置"},
    "tx_element_pattern_figure": {"relative_path": "figures/tx_element_pattern.png", "label": "Tx 单元因子图", "category": "analysis", "description": "单个发射阵元方向图可视化"},
    "tx_radiation_pattern": {"relative_path": "analysis/tx_radiation_pattern.npz", "label": "Tx 合成方向图", "category": "analysis", "description": "单元因子与发射阵列因子合成后的方向图"},
    "tx_radiation_pattern_figure": {"relative_path": "figures/tx_radiation_pattern.png", "label": "Tx 合成方向图图像", "category": "analysis", "description": "发射阵列最终辐射方向图可视化"},
    "rx_element_pattern": {"relative_path": "analysis/rx_element_pattern.npz", "label": "Rx 单元因子", "category": "analysis", "description": "单个接收阵元方向图增益网格"},
    "rx_element_pattern_figure": {"relative_path": "figures/rx_element_pattern.png", "label": "Rx 单元因子图", "category": "analysis", "description": "单个接收阵元方向图可视化"},
    "rx_steering_pattern": {"relative_path": "analysis/rx_steering_pattern.npz", "label": "Rx 阵列方向图", "category": "analysis", "description": "包含单元因子后的接收阵列合成方向图"},
    "rx_steering_pattern_figure": {"relative_path": "figures/rx_steering_pattern.png", "label": "Rx 阵列方向图图像", "category": "analysis", "description": "包含单元因子后的接收阵列方向图可视化"},
}


def artifact_path(run_dir: Path, artifact_id: str) -> Path:
    spec = ARTIFACTS.get(artifact_id)
    if spec is None:
        raise KeyError(f"Unknown download artifact: {artifact_id}")
    path = (run_dir / spec["relative_path"]).resolve()
    root = run_dir.resolve()
    if root not in path.parents:
        raise ValueError("Artifact path escapes run directory")
    return path


def download_catalog(run_dir: Path, run_id: str) -> list[dict[str, Any]]:
    items = [
        {
            "artifact_id": "analysis_bundle",
            "label": "分析结果包",
            "category": "bundle",
            "description": "配置、摘要、MPC、FMCW、波束和图像；不含 CIR、原始路径和完整路径表",
            "size_bytes": None,
            "generated": True,
            "download_url": f"/api/results/{run_id}/downloads/analysis_bundle",
        },
        {
            "artifact_id": "full_bundle",
            "label": "完整结果包",
            "category": "bundle",
            "description": "包含完整 CIR、传播路径数组、完整路径表和全部分析结果",
            "size_bytes": None,
            "generated": True,
            "download_url": f"/api/results/{run_id}/result_bundle.zip",
        },
    ]
    for artifact_id, spec in ARTIFACTS.items():
        path = artifact_path(run_dir, artifact_id)
        if not path.exists():
            continue
        items.append(
            {
                "artifact_id": artifact_id,
                "label": spec["label"],
                "category": spec["category"],
                "description": spec["description"],
                "size_bytes": path.stat().st_size,
                "generated": False,
                "download_url": f"/api/results/{run_id}/downloads/{artifact_id}",
            }
        )
    return items


def build_analysis_bundle(run_dir: Path, bundle_root: Path) -> Path:
    bundle_root.mkdir(parents=True, exist_ok=True)
    zip_path = bundle_root / f"{run_dir.name}_analysis_bundle.zip"
    included: list[str] = []
    excluded_analysis = {"paths.csv", "beamformed_observation.npz"}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ("config.yaml", "metadata.json", "metrics.json"):
            path = run_dir / name
            if path.exists():
                arcname = f"configs/{name}"
                archive.write(path, arcname)
                included.append(arcname)
        analysis_dir = run_dir / "analysis"
        if analysis_dir.exists():
            for path in sorted(analysis_dir.iterdir()):
                if not path.is_file() or path.name in excluded_analysis:
                    continue
                arcname = f"analysis/{path.name}"
                archive.write(path, arcname)
                included.append(arcname)
        figures_dir = run_dir / "figures"
        if figures_dir.exists():
            for path in sorted(figures_dir.glob("*.png")):
                arcname = f"figures/{path.name}"
                archive.write(path, arcname)
                included.append(arcname)
        manifest = {
            "schema_version": "0.1.0",
            "run_id": run_dir.name,
            "created_at_utc": utc_now(),
            "bundle_kind": "analysis_without_large_raw_arrays",
            "excluded": ["cir.npz", "paths_summary.npz", "paths_per_element.npz", "radar_observation.npz", "analysis/paths.csv", "analysis/beamformed_observation.npz"],
            "included_files": included,
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    return zip_path
