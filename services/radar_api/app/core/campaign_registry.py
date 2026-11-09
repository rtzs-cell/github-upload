from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import Settings
from app.schemas import CampaignSummary, RunSummary


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    display_name: str
    root: Path
    readonly: bool = True
    created_at_utc: str | None = None
    source_experiment_id: str | None = None

    @property
    def pose_metrics_path(self) -> Path:
        return self.root / "reports" / "POSE_METRICS.csv"


class CampaignRegistry:
    LOCAL_RESULTS_ID = "workbench_local"
    REQUIRED_RUN_FILES = (
        "config.yaml",
        "metadata.json",
        "metrics.json",
        "paths_summary.npz",
        "radar_observation.npz",
    )

    def __init__(self, settings: Settings):
        self.settings = settings
        builtin_campaigns = {
            "c002_full_existing": Campaign(
                campaign_id="c002_full_existing",
                display_name="C002 Full Radar Sensing",
                root=settings.existing_campaign_root,
                readonly=True,
            )
        }
        self._builtin_campaigns = builtin_campaigns if settings.existing_campaign_root.exists() else {}

    def _workbench_campaigns(self) -> list[Campaign]:
        campaigns_root = self.settings.workbench_output_root / "campaigns"
        campaigns: list[Campaign] = []
        if not campaigns_root.exists():
            return campaigns
        for path in sorted(campaigns_root.iterdir()):
            if not path.is_dir():
                continue
            manifest = path / "campaign_manifest.json"
            display_name = path.name
            created_at_utc = None
            source_experiment_id = None
            if manifest.exists():
                try:
                    with manifest.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    display_name = str(data.get("display_name", display_name))
                    created_at_utc = data.get("created_at_utc")
                    source_experiment_id = data.get("request", {}).get("source_experiment_id")
                except Exception:
                    pass
            campaigns.append(
                Campaign(
                    campaign_id=path.name,
                    display_name=display_name,
                    root=path,
                    readonly=False,
                    created_at_utc=created_at_utc,
                    source_experiment_id=source_experiment_id,
                )
            )
        return campaigns

    def _all_campaigns(self) -> list[Campaign]:
        return [*self._builtin_campaigns.values(), *self._workbench_campaigns()]

    @staticmethod
    def _read_table(path: Path) -> pd.DataFrame:
        return pd.read_csv(path)

    @staticmethod
    def _table_path(campaign: Campaign) -> Path | None:
        for path in (campaign.pose_metrics_path, campaign.root / "reports" / "runs_index.csv"):
            if path.exists():
                return path
        return None

    def _complete_rows(self, campaign: Campaign) -> list[dict[str, Any]]:
        table_path = self._table_path(campaign)
        if table_path is None:
            return []
        try:
            rows = self._read_table(table_path).to_dict(orient="records")
        except (OSError, UnicodeError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
            return []
        complete: list[dict[str, Any]] = []
        for row in rows:
            run_id = str(row.get("run_id") or "").strip()
            run_dir = campaign.root / "runs" / run_id
            if run_id and run_dir.is_dir() and all((run_dir / name).is_file() for name in self.REQUIRED_RUN_FILES):
                complete.append(row)
        return complete

    def list_campaigns(self) -> list[CampaignSummary]:
        summaries: list[CampaignSummary] = []
        for campaign in self._all_campaigns():
            run_count = len(self._complete_rows(campaign))
            if not campaign.readonly and run_count == 0:
                continue
            summaries.append(
                CampaignSummary(
                    campaign_id=campaign.campaign_id,
                    display_name=campaign.display_name,
                    root=str(campaign.root),
                    run_count=run_count,
                    readonly=campaign.readonly,
                    created_at_utc=campaign.created_at_utc,
                    source_experiment_id=campaign.source_experiment_id,
                )
            )
        workbench_campaigns = [
            campaign for campaign in self._workbench_campaigns()
            if not campaign.campaign_id.startswith("tiny_")
        ]
        summaries.insert(
            1 if self._builtin_campaigns else 0,
            CampaignSummary(
                campaign_id=self.LOCAL_RESULTS_ID,
                display_name="我的仿真结果",
                root=str(self.settings.workbench_output_root / "campaigns"),
                run_count=sum(self._campaign_run_count(campaign) for campaign in workbench_campaigns),
                readonly=False,
            ),
        )
        return summaries

    def _campaign_run_count(self, campaign: Campaign) -> int:
        return len(self._complete_rows(campaign))

    def get_campaign(self, campaign_id: str) -> Campaign:
        for campaign in self._all_campaigns():
            if campaign.campaign_id == campaign_id:
                return campaign
        raise KeyError(f"Unknown campaign_id: {campaign_id}")

    def load_runs(self, campaign_id: str) -> list[RunSummary]:
        if campaign_id == self.LOCAL_RESULTS_ID:
            runs: list[RunSummary] = []
            campaigns = sorted(
                [
                    campaign for campaign in self._workbench_campaigns()
                    if not campaign.campaign_id.startswith("tiny_")
                ],
                key=lambda item: item.created_at_utc or item.campaign_id,
                reverse=True,
            )
            for campaign in campaigns:
                runs.extend(self._load_campaign_runs(campaign))
            return runs
        campaign = self.get_campaign(campaign_id)
        return self._load_campaign_runs(campaign)

    def _load_campaign_runs(self, campaign: Campaign) -> list[RunSummary]:
        summaries: list[RunSummary] = []
        for row in self._complete_rows(campaign):
            try:
                summaries.append(self._row_to_run_summary(row, campaign))
            except (KeyError, TypeError, ValueError):
                continue
        return summaries

    def build_run_index(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        for campaign in self._all_campaigns():
            for row in self._complete_rows(campaign):
                run_id = str(row["run_id"])
                run_dir = campaign.root / "runs" / run_id
                index[run_id] = run_dir
        return index

    def _row_to_run_summary(self, row: dict[str, Any], campaign: Campaign) -> RunSummary:
        run_id = str(row["run_id"])
        display_name = None
        label_path = campaign.root / "runs" / run_id / "display_name.json"
        if label_path.exists():
            try:
                with label_path.open("r", encoding="utf-8") as f:
                    display_name = str(json.load(f).get("display_name") or "").strip() or None
            except (OSError, ValueError, TypeError):
                display_name = None
        return RunSummary(
            run_id=run_id,
            pose_id=str(row["pose_id"]),
            boresight_id=str(row["boresight_id"]),
            x_m=float(row["x_m"]),
            y_m=float(row["y_m"]),
            z_m=float(row["z_m"]),
            look_x_m=float(row["look_x_m"]),
            look_y_m=float(row["look_y_m"]),
            look_z_m=float(row["look_z_m"]),
            boresight_az_deg=float(row["boresight_az_deg"]),
            boresight_el_deg=float(row["boresight_el_deg"]),
            valid_path_count=int(row["valid_path_count"]),
            dominant_range_m=float(row["dominant_range_m"]),
            range_max_m=float(row["range_max_m"]),
            fov_energy_fraction=float(row["fov_energy_fraction"]),
            fov_path_fraction=float(row["fov_path_fraction"]),
            energy_in_fov=float(row["energy_in_fov"]),
            max_interaction_depth=int(row["max_interaction_depth"]),
            samples_per_src=int(row["samples_per_src"]),
            seed=int(row["seed"]),
            status="complete",
            campaign_id=campaign.campaign_id,
            created_at_utc=campaign.created_at_utc,
            source_experiment_id=campaign.source_experiment_id,
            display_name=display_name,
        )
