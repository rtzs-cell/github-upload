from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CampaignSummary(BaseModel):
    campaign_id: str
    display_name: str
    root: str
    run_count: int
    readonly: bool = True
    created_at_utc: str | None = None
    source_experiment_id: str | None = None


class CampaignListResponse(BaseModel):
    campaigns: list[CampaignSummary]


class RunSummary(BaseModel):
    run_id: str
    pose_id: str
    boresight_id: str
    x_m: float
    y_m: float
    z_m: float
    look_x_m: float
    look_y_m: float
    look_z_m: float
    boresight_az_deg: float
    boresight_el_deg: float
    valid_path_count: int
    dominant_range_m: float
    range_max_m: float
    fov_energy_fraction: float
    fov_path_fraction: float
    energy_in_fov: float
    max_interaction_depth: int
    samples_per_src: int
    seed: int
    status: str = "complete"
    campaign_id: str | None = None
    created_at_utc: str | None = None
    source_experiment_id: str | None = None
    display_name: str | None = None


class RunsResponse(BaseModel):
    campaign_id: str
    runs: list[RunSummary]


class ArtifactAvailability(BaseModel):
    top_paths: bool
    first_interactions: bool
    range_azimuth: bool
    range_elevation: bool
    cir: bool = False


class RunMetadataResponse(BaseModel):
    run_id: str
    config: dict[str, Any]
    metadata: dict[str, Any]
    metrics: dict[str, Any]
    available_artifacts: ArtifactAvailability


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    allowed_gpu_ids: list[int]
    existing_campaign_available: bool
    web_cache_root: str
    sionna_runtime: dict[str, Any] = Field(default_factory=dict)


class SceneObjectsResponse(BaseModel):
    run_id: str
    objects: list[dict[str, Any]]


class TopPathsResponse(BaseModel):
    schema_version: str
    run_id: str
    selection: dict[str, Any]
    paths: list[dict[str, Any]]


class PathExportRequest(BaseModel):
    draft_config: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=1000, ge=1, le=5000)
    kind: Literal["all", "specular", "diffuse", "mixed", "unknown"] = "all"
    in_fov: bool = True
    note: str | None = None


class PathExportResponse(BaseModel):
    export_id: str
    run_id: str
    root: str
    path_count: int
    files: dict[str, str]


class InteractionsResponse(BaseModel):
    run_id: str
    columns: list[str]
    interactions: list[dict[str, Any]]


class SpectrumMetadata(BaseModel):
    run_id: str
    kind: Literal["range_azimuth", "range_elevation"]
    dtype: str
    shape: list[int]
    layout: str = "row-major"
    array_url: str
    range_edges_m: list[float] = Field(default_factory=list)
    angle_edges_deg: list[float] = Field(default_factory=list)
    angle_label: str
    scale: str = "linear_power"
    recommended_display: dict[str, Any] = Field(
        default_factory=lambda: {"scale": "db", "dynamic_range_db": 60}
    )


class ExperimentCreateRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class OsmFetchRequest(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    radius_km: float = Field(default=1.0, gt=0.0, le=5.0)


class OsmBboxFetchRequest(BaseModel):
    south: float = Field(ge=-90.0, le=90.0)
    west: float = Field(ge=-180.0, le=180.0)
    north: float = Field(ge=-90.0, le=90.0)
    east: float = Field(ge=-180.0, le=180.0)


class NameUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ExperimentUpdateRequest(BaseModel):
    config: dict[str, Any]


class ExperimentSummary(BaseModel):
    schema_version: str
    experiment_id: str
    name: str
    created_at_utc: str
    status: str
    root: str
    files: dict[str, str] = Field(default_factory=dict)


class ExperimentListResponse(BaseModel):
    experiments: list[ExperimentSummary]


class ExperimentResponse(BaseModel):
    manifest: ExperimentSummary
    config: dict[str, Any]


class PathStatisticsResponse(BaseModel):
    summary: dict[str, Any]
    files: dict[str, str]


class ResultBundleResponse(BaseModel):
    run_id: str
    bundle_path: str


class DownloadArtifact(BaseModel):
    artifact_id: str
    label: str
    category: str
    description: str
    size_bytes: int | None = None
    generated: bool = False
    download_url: str


class DownloadCatalogResponse(BaseModel):
    run_id: str
    artifacts: list[DownloadArtifact]


class BeamformingResponse(BaseModel):
    summary: dict[str, Any]
    files: dict[str, str]


class AnalysisArtifactsResponse(BaseModel):
    summary: dict[str, Any]
    files: dict[str, str]


class RadarVector3(BaseModel):
    x: float
    y: float
    z: float


class ArrayConfig(BaseModel):
    num_rows: int
    num_cols: int
    vertical_spacing: float = 0.5
    horizontal_spacing: float = 0.5
    pattern: str = "iso"
    polarization: str = "V"
    gain_grid_json: str | None = None
    element_pattern: str | None = None
    element_gain_grid_json: str | None = None

    @model_validator(mode="after")
    def validate_custom_gain(self) -> "ArrayConfig":
        if self.pattern == "custom_gain_grid":
            if not self.gain_grid_json:
                raise ValueError("custom_gain_grid requires gain_grid_json")
            from sionna_radar.antenna_patterns import parse_custom_gain_grid

            parse_custom_gain_grid(self.gain_grid_json)
        if self.pattern == "radar_array":
            element_pattern = str(self.element_pattern or "tr38901")
            if element_pattern not in {"iso", "isotropic", "tr38901", "custom_gain_grid"}:
                raise ValueError(f"Unknown Tx element pattern: {element_pattern}")
            if element_pattern == "custom_gain_grid":
                if not self.element_gain_grid_json:
                    raise ValueError("custom Tx element pattern requires element_gain_grid_json")
                from sionna_radar.antenna_patterns import parse_custom_gain_grid

                parse_custom_gain_grid(self.element_gain_grid_json)
        return self


class InitialRaySamplingConfig(BaseModel):
    mode: Literal["full_sphere", "analysis_sector"] = "full_sphere"
    azimuth_center_deg: float | None = None
    azimuth_width_deg: float | None = None
    elevation_min_deg: float | None = None
    elevation_max_deg: float | None = None


class PathSolverConfig(BaseModel):
    max_depth: int = 2
    max_num_paths_per_src: int = 1_000_000
    samples_per_src: int = 500_000
    synthetic_array: bool = True
    los: bool = False
    specular_reflection: bool = True
    diffuse_reflection: bool = True
    refraction: bool = False
    diffraction: bool = False
    edge_diffraction: bool = False
    seed: int = 501
    initial_ray_sampling: InitialRaySamplingConfig = Field(default_factory=InitialRaySamplingConfig)


class ScatteringConfig(BaseModel):
    enabled: bool = True
    coefficient: float = 0.5
    pattern: Literal["backscattering", "lambertian", "directive"] = "backscattering"
    alpha_r: int = 20
    alpha_i: int = 20
    lambda_: float = 0.3
    xpd_coefficient: float = 0.0


class CirNoiseConfig(BaseModel):
    enabled: bool = False
    snr_db: float = Field(default=20.0, ge=-100.0, le=200.0)
    seed: int = 1001


class RadarSimulationRequest(BaseModel):
    scene_id: str
    scene_geometry: dict[str, Any] | None = None
    source_experiment_id: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    mode: Literal["single_pose", "campaign"] = "single_pose"
    radar: dict[str, Any]
    poses: list[dict[str, Any]] = Field(default_factory=list)
    propagation: dict[str, Any]
    waveform: dict[str, Any] = Field(default_factory=dict)
    receiver: dict[str, Any] = Field(default_factory=dict)
    radar_processing: dict[str, Any] = Field(default_factory=dict)
    scattering: ScatteringConfig = Field(default_factory=ScatteringConfig)
    tx_array: ArrayConfig
    rx_array: ArrayConfig
    path_solver: PathSolverConfig = Field(default_factory=PathSolverConfig)
    observation: dict[str, Any] = Field(default_factory=dict)
    compute: dict[str, Any] = Field(default_factory=dict)
    cir_noise: CirNoiseConfig = Field(default_factory=CirNoiseConfig)
    gpu_ids: list[int] = Field(default_factory=lambda: [0, 1, 2, 3])

    @model_validator(mode="after")
    def validate_tx_complex_weights(self) -> "RadarSimulationRequest":
        beamforming = dict(self.observation.get("beamforming", {}) or {})
        mode = str(beamforming.get("tx_weight_mode", "steering_vector"))
        if mode not in {"steering_vector", "custom_complex_weights"}:
            raise ValueError(f"Unknown Tx weight mode: {mode}")
        if mode == "custom_complex_weights" and self.tx_array.pattern != "custom_gain_grid":
            from sionna_radar.antenna_patterns import parse_complex_weights

            raw = beamforming.get("tx_custom_weights_json")
            if not raw:
                raise ValueError("custom Tx weight mode requires tx_custom_weights_json")
            parse_complex_weights(raw, self.tx_array.num_rows * self.tx_array.num_cols, "Tx")
        return self


class SimulationJobResponse(BaseModel):
    job_id: str
    status: str
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    created_at_utc: str
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    progress: dict[str, int] = Field(default_factory=dict)
    gpu_ids: list[int] = Field(default_factory=list)
    current_tasks: list[dict[str, Any]] = Field(default_factory=list)
    available_run_ids: list[str] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
