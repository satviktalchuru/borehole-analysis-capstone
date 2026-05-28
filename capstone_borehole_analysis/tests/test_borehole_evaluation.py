import json
import tempfile
import unittest
from pathlib import Path

import trimesh

from borehole_evaluation import evaluate_runs, markdown_report


class BoreholeEvaluationTests(unittest.TestCase):
    def make_run(self, root: Path, name: str, summary: dict, watertight: bool = True) -> Path:
        run_dir = root / name
        run_dir.mkdir()
        mesh = trimesh.creation.cylinder(radius=0.05, height=1.0, sections=16)
        if not watertight:
            mesh.update_faces(range(len(mesh.faces) - 1))
        mesh.export(run_dir / "borehole_final_smooth.stl")
        (run_dir / "borehole_summary.json").write_text(json.dumps(summary))
        (run_dir / "borehole_slice_metrics.csv").write_text("slice_index,cavity_quality\n0,0.5\n")
        return run_dir

    def test_evaluate_runs_summarizes_mesh_and_reconstruction_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(
                root,
                "outputs_a",
                {
                    "accepted_slices": 9,
                    "total_centerline_slices": 10,
                    "slice_success_rate": 0.9,
                    "mean_cavity_quality": 0.2,
                    "max_radius_jump": 0.01,
                    "radius_roughness_cv": 0.03,
                },
            )

            rows = evaluate_runs({"case-a": run})

            self.assertEqual(rows[0]["dataset"], "case-a")
            self.assertEqual(rows[0]["accepted_slices"], 9)
            self.assertTrue(rows[0]["mesh_watertight"])
            self.assertEqual(rows[0]["mesh_components"], 1)

    def test_markdown_report_orders_core_metrics_into_table(self):
        rows = [
            {
                "dataset": "case-a",
                "accepted_slices": 9,
                "total_centerline_slices": 10,
                "mesh_watertight": True,
                "mesh_components": 1,
                "mean_cavity_quality": 0.2,
                "max_radius_jump": 0.01,
                "radius_roughness_cv": 0.03,
            }
        ]

        report = markdown_report(rows)

        self.assertIn("| Dataset | Accepted Slices | Watertight | Components | Cavity Quality | Max Radius Jump | Roughness CV |", report)
        self.assertIn("| case-a | 9/10 | yes | 1 | 0.2000 | 0.010000 | 0.0300 |", report)


if __name__ == "__main__":
    unittest.main()
