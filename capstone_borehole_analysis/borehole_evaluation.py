#!/usr/bin/env python3
"""Compare borehole reconstruction outputs across simulation runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import trimesh


CORE_FIELDS = [
    "accepted_slices",
    "total_centerline_slices",
    "slice_success_rate",
    "mean_cavity_quality",
    "max_radius_jump",
    "radius_roughness_cv",
    "mean_inlier_ratio",
    "regularized_radius_outliers",
    "ransac_candidates",
]


def load_run_metrics(dataset: str, run_dir: Path) -> dict:
    summary_path = run_dir / "borehole_summary.json"
    stl_path = run_dir / "borehole_final_smooth.stl"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary file: {summary_path}")
    if not stl_path.exists():
        raise FileNotFoundError(f"Missing STL file: {stl_path}")

    summary = json.loads(summary_path.read_text())
    mesh = trimesh.load_mesh(stl_path)
    row = {"dataset": dataset, "run_dir": str(run_dir)}
    for field in CORE_FIELDS:
        row[field] = summary.get(field, 0)
    row["mesh_watertight"] = bool(mesh.is_watertight)
    row["mesh_components"] = int(len(mesh.split(only_watertight=False)))
    row["mesh_vertices"] = int(len(mesh.vertices))
    row["mesh_faces"] = int(len(mesh.faces))
    row["mesh_bounds_x"] = float(mesh.bounds[1][0] - mesh.bounds[0][0])
    row["mesh_bounds_y"] = float(mesh.bounds[1][1] - mesh.bounds[0][1])
    row["mesh_bounds_z"] = float(mesh.bounds[1][2] - mesh.bounds[0][2])
    return row


def evaluate_runs(run_dirs: dict[str, Path]) -> list[dict]:
    return [load_run_metrics(dataset, Path(run_dir)) for dataset, run_dir in run_dirs.items()]


def _fmt(value: object, digits: int = 4) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_report(rows: list[dict]) -> str:
    lines = [
        "# Borehole Reconstruction Evaluation",
        "",
        "| Dataset | Accepted Slices | Watertight | Components | Cavity Quality | Max Radius Jump | Roughness CV |",
        "|---|---:|:---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        accepted = f"{row['accepted_slices']}/{row['total_centerline_slices']}"
        lines.append(
            "| {dataset} | {accepted} | {watertight} | {components} | {quality} | {jump} | {roughness} |".format(
                dataset=row["dataset"],
                accepted=accepted,
                watertight=_fmt(row["mesh_watertight"]),
                components=row["mesh_components"],
                quality=_fmt(float(row["mean_cavity_quality"])),
                jump=_fmt(float(row["max_radius_jump"]), digits=6),
                roughness=_fmt(float(row["radius_roughness_cv"])),
            )
        )
    lines.extend(
        [
            "",
            "Lower `max_radius_jump` and `radius_roughness_cv` indicate smoother radius continuity. ",
            "Higher `mean_cavity_quality` indicates better agreement between the fitted cavity boundary and local point-cloud evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="append",
        nargs=2,
        metavar=("NAME", "DIR"),
        required=True,
        help="Dataset label and output directory to evaluate.",
    )
    parser.add_argument("--out-dir", default="docs")
    args = parser.parse_args()

    runs = {name: Path(directory) for name, directory in args.run}
    rows = evaluate_runs(runs)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "model_evaluation.csv", rows)
    (out_dir / "model_evaluation.md").write_text(markdown_report(rows))
    print(markdown_report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
