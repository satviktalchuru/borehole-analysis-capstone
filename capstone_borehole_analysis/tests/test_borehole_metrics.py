import unittest

import numpy as np

from borehole_metrics import (
    ellipse_level_set,
    ellipse_pixel_confusion,
    perimeter_completeness,
    summarize_radius_continuity,
)


class BoreholeMetricTests(unittest.TestCase):
    def test_ellipse_level_set_is_negative_inside_and_positive_outside(self):
        pts = np.array([[0.0, 0.0], [2.0, 0.0], [3.0, 0.0], [0.0, 1.0]])

        values = ellipse_level_set(pts, center=(0.0, 0.0), axes=(2.0, 1.0), angle_rad=0.0)

        self.assertLess(values[0], 0.0)
        self.assertAlmostEqual(values[1], 0.0)
        self.assertGreater(values[2], 0.0)
        self.assertAlmostEqual(values[3], 0.0)

    def test_pixel_confusion_counts_soil_inside_and_void_outside_boundary(self):
        points = np.array([[0.0, 0.0], [2.5, 0.0]])

        metrics = ellipse_pixel_confusion(
            points,
            center=(0.0, 0.0),
            axes=(1.0, 1.0),
            angle_rad=0.0,
            soil_radius=2.0,
            grid_res=41,
        )

        self.assertGreater(metrics["soil_inside_pixels"], 0)
        self.assertGreater(metrics["void_outside_pixels"], 0)
        self.assertEqual(metrics["total_pixels"], metrics["inside_pixels"] + metrics["outside_pixels"])
        self.assertLessEqual(metrics["balanced_accuracy"], 1.0)
        self.assertGreaterEqual(metrics["balanced_accuracy"], 0.0)

    def test_perimeter_completeness_detects_partial_boundary_coverage(self):
        angles = np.linspace(0.0, np.pi, 24)
        candidates = np.column_stack([np.cos(angles), np.sin(angles)])

        completeness = perimeter_completeness(
            candidates,
            center=(0.0, 0.0),
            axes=(1.0, 1.0),
            angle_rad=0.0,
            samples=36,
            tolerance=0.08,
        )

        self.assertGreater(completeness, 0.35)
        self.assertLess(completeness, 0.75)

    def test_radius_continuity_reports_jumps_and_relative_roughness(self):
        metrics = summarize_radius_continuity(np.array([1.0, 1.0, 1.2, 1.2]))

        self.assertAlmostEqual(metrics["max_radius_jump"], 0.2)
        self.assertGreater(metrics["radius_diff_std"], 0.0)
        self.assertGreater(metrics["radius_roughness_cv"], 0.0)


if __name__ == "__main__":
    unittest.main()
