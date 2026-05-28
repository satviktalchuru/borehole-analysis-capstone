import unittest

import numpy as np

from borehole_piecewise_surface import (
    choose_global_fit_sequence,
    fit_ransac_model,
    loft_rings_to_mesh,
    parallel_transport_frames,
    radial_boundary_candidates,
    regularize_slice_fits,
    ransac_ellipse,
)


class PiecewiseSurfaceGeometryTests(unittest.TestCase):
    def test_loft_rings_to_mesh_caps_ends_for_watertight_surface(self):
        lower = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [-1.0, 0.0, 0.0],
                [0.0, -1.0, 0.0],
            ]
        )
        upper = lower + np.array([0.0, 0.0, 2.0])

        mesh = loft_rings_to_mesh([lower, upper])

        self.assertTrue(mesh.is_watertight)
        self.assertEqual(len(mesh.vertices), 10)
        self.assertEqual(len(mesh.faces), 16)

    def test_parallel_transport_frames_are_orthonormal_and_smooth(self):
        t = np.linspace(0.0, 1.0, 12)
        centers = np.column_stack([t, 0.08 * np.sin(t * np.pi), 0.04 * np.cos(t * np.pi)])
        tangents, e1, e2 = parallel_transport_frames(centers)

        for i in range(len(centers)):
            self.assertAlmostEqual(float(np.dot(tangents[i], e1[i])), 0.0, places=6)
            self.assertAlmostEqual(float(np.dot(tangents[i], e2[i])), 0.0, places=6)
            self.assertAlmostEqual(float(np.dot(e1[i], e2[i])), 0.0, places=6)
            self.assertAlmostEqual(float(np.linalg.norm(e1[i])), 1.0, places=6)
            self.assertAlmostEqual(float(np.linalg.norm(e2[i])), 1.0, places=6)

        frame_steps = np.linalg.norm(np.diff(e1, axis=0), axis=1)
        self.assertLess(float(frame_steps.max()), 0.2)

    def test_regularize_slice_fits_interpolates_radius_spikes(self):
        fits = []
        for i, radius in enumerate([0.05, 0.051, 0.12, 0.052, 0.05]):
            fits.append(
                {
                    "fit": {"cx": 0.0, "cy": 0.0, "a": radius, "b": radius, "theta": 0.0},
                    "row": {"equivalent_radius": radius, "cavity_quality": 0.8},
                }
            )

        params, rejected = regularize_slice_fits(fits, circularity_prior=1.0, outlier_mad=3.0, window_size=5)

        self.assertEqual(rejected, 1)
        self.assertLess(params["axis_a"][2], 0.06)
        self.assertLess(float(np.max(np.abs(np.diff(params["equivalent_radius"])))), 0.005)

    def test_fit_ransac_model_supports_installed_scikit_image_api(self):
        angles = np.linspace(0.0, 2.0 * np.pi, 80, endpoint=False)
        pts = np.column_stack([0.04 * np.cos(angles), 0.03 * np.sin(angles)])

        model, inliers = fit_ransac_model(pts, max_trials=20, tol=0.004, random_state=7)

        self.assertIsNotNone(model)
        self.assertGreater(int(inliers.sum()), 50)

    def test_ransac_ellipse_returns_normalized_parameters(self):
        angles = np.linspace(0.0, 2.0 * np.pi, 100, endpoint=False)
        pts = np.column_stack([0.04 * np.cos(angles), 0.03 * np.sin(angles)])

        fit = ransac_ellipse(pts, tol=0.004, min_inlier_frac=0.5, max_axis_ratio=3.0, max_trials=30, random_state=3)

        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit["cx"], 0.0, places=3)
        self.assertAlmostEqual(fit["cy"], 0.0, places=3)
        self.assertGreater(fit["a"], 0.025)
        self.assertGreater(fit["b"], 0.025)

    def test_global_fit_sequence_prefers_smooth_path_over_local_spike(self):
        def candidate(radius, quality):
            return {
                "fit": {"cx": 0.0, "cy": 0.0, "a": radius, "b": radius, "theta": 0.0},
                "row": {"equivalent_radius": radius, "cavity_quality": quality},
            }

        candidates = [
            [candidate(0.050, 0.90)],
            [candidate(0.090, 0.99), candidate(0.052, 0.85)],
            [candidate(0.051, 0.90)],
        ]

        selected = choose_global_fit_sequence(candidates, smoothness_weight=8.0)

        self.assertEqual([round(item["row"]["equivalent_radius"], 3) for item in selected], [0.05, 0.052, 0.051])

    def test_radial_boundary_candidates_prefers_outer_envelope_per_angle_bin(self):
        angles = np.linspace(0.0, 2.0 * np.pi, 64, endpoint=False)
        inner = np.column_stack([0.03 * np.cos(angles), 0.03 * np.sin(angles)])
        outer = np.column_stack([0.05 * np.cos(angles), 0.05 * np.sin(angles)])
        pts = np.vstack([inner, outer])

        boundary = radial_boundary_candidates(pts, angle_bins=32, min_bin_points=2, quantile=0.9)
        radii = np.linalg.norm(boundary, axis=1)

        self.assertGreaterEqual(boundary.shape[0], 24)
        self.assertGreater(float(np.mean(radii)), 0.045)
        self.assertLess(float(np.std(radii)), 0.004)


if __name__ == "__main__":
    unittest.main()
