from pathlib import Path

from app.core.scene_object_mapping import object_index_map


def test_object_index_map_follows_scene_shape_order(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene.xml"
    scene_path.write_text(
        """<scene version="2.1.0">
  <shape type="ply" id="mesh-floor" />
  <shape type="ply" id="mesh-building_A" />
  <shape type="ply" id="mesh-building_B" />
</scene>
""",
        encoding="utf-8",
    )
    metadata = {
        "scene_path": str(scene_path),
        "scene_geometry": {
            "objects": {
                "building_A": {},
                "building_B": {},
                "floor": {},
            }
        },
    }

    assert object_index_map(metadata) == {1: "floor", 2: "building_A", 3: "building_B"}


def test_object_index_map_falls_back_to_metadata_order() -> None:
    metadata = {"scene_geometry": {"objects": {"building_A": {}, "floor": {}}}}
    assert object_index_map(metadata) == {1: "building_A", 2: "floor"}
