"""Plan-only Skybind bootstrap invariants. Deliberately NOT a product gate."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/roadmap"
TARGETS = {"skybind", "skybind_webui", "skybind_runtime_inputs", "skybind_android_device", "skybind_release"}


def load():
    with (ROOT / ".devtool.toml").open("rb") as file:
        cfg = tomllib.load(file)
    index = json.loads((DOCS / "SKYBIND_DEVTOOL_OVERLAY_INDEX.json").read_text())
    return cfg, index


def check_all():
    cfg, data = load()
    assert cfg["workspace"]["default_target"] == "skybind"
    assert TARGETS == set(cfg["targets"]), "Unexpected/absent canonical target"
    for target in cfg["targets"].values():
        assert (ROOT / target["root"]).is_dir()
        assert "bootstrap" in target["workflows"]
    for name in ("SKYBIND_FEATURE_SPEC.md", "SKYBIND_DEVTOOL_ROADMAP.md"):
        assert (DOCS / name).is_file(), name
    assert data["product"] == "skybind"
    assert data["status"] == "PLANNED"
    assert (data["implementation_count"], data["gate_count"], data["seal_count"]) == (36, 8, 1)
    assert (len(data["implementation_overlays"]), len(data["gate_overlays"])) == (36, 8)
    assert data["typed_api_count"] == len(data["typed_api_operations"]) == 57
    impl = data["implementation_overlays"]
    gates = data["gate_overlays"]
    seal = data["final_seal"]
    overlays = impl + gates + [seal]
    all_ids = [entry["id"] for entry in overlays]
    assert len(all_ids) == len(set(all_ids)) == 45
    assert len(set(all_ids).intersection({"SB-O01", "SB-O36", "SB-G01", "SB-G08", "SB-FS1"})) == 5
    edges = {entry["id"]: entry.get("dependencies", []) for entry in overlays}
    for src, parents in edges.items():
        assert len(parents) == len(set(parents)), src
        assert all(parent in edges for parent in parents), src
    visited = set()
    active = set()
    def visit(key):
        assert key not in active, f"Dependency cycle at {key}"
        if key in visited:
            return
        active.add(key)
        for parent in edges[key]:
            visit(parent)
        active.remove(key)
        visited.add(key)
    for key in edges:
        visit(key)
    assert all(item.get("status") == "PLANNED" for item in impl + gates)
    assert seal.get("status") == "PLANNED"
    assert "direct source copy" in data["webui_policy"]
    exclusions = " ".join(data["explicit_exclusions"]).lower()
    assert "dynamic runtime" in exclusions and "migration" in exclusions
    for name, entry in cfg["wrapper"]["commands"].items():
        assert entry["workflow"] in {"bootstrap", "foundation", "native"}, f"{name}: unexpected workflow"
        if entry["workflow"] != "bootstrap":
            assert name in {"foundation", "native"}, "Unqualified workflow not allowed"
    assert not any("seal" in key for target in cfg["targets"].values() for key in target["workflows"])
    return cfg, data


def check_component(component):
    _, data = check_all()
    if component == "webui":
        assert "visual/interaction parity mandatory" in data["webui_policy"]
    elif component == "runtime":
        assert data["identity"]["upstream_engine_binary"] == "system/bin/rclone"
        assert "installed dynamic runtime" in " ".join(data["explicit_exclusions"]).lower()
    elif component == "android":
        assert any("device" in json.dumps(item).lower() for item in data["gate_overlays"])
    elif component == "release":
        assert data["final_seal"]["status"] == "PLANNED"
    else:
        raise ValueError(f"Unknown bootstrap component: {component}")
    return f"SKYBIND {component}: planning contract checked; implementation/device/seal NOT certified"
