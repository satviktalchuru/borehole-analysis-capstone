"""Metrics for evaluating fitted borehole cross-sections.

The functions in this module are intentionally geometry-only so they can be
unit tested without loading the full VTK/STL data set.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def _rotation_matrix(angle_rad: float) -> np.ndarray:
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return np.array([[c, -s], [s, c]], dtype=float)


def ellipse_level_set(
    points2d: np.ndarray,
    center: tuple[float, float],
    axes: tuple[float, float],
    angle_rad: float = 0.0,
) -> np.ndarray:
    """Return normalized ellipse level-set values.

    Values are negative inside the ellipse, zero on the boundary, and positive
    outside. Axes are semi-axis lengths.
    """
    pts = np.asarray(points2d, dtype=float)
    cx, cy = center
    a, b = axes
    if a <= 0 or b <= 0:
        raise ValueError("Ellipse axes must be positive.")

    rel = pts - np.array([cx, cy], dtype=float)
    local = rel @ _rotation_matrix(angle_rad)
    return (local[:, 0] / a) ** 2 + (local[:, 1] / b) ** 2 - 1.0


def ellipse_boundary_points(
    center: tuple[float, float],
    axes: tuple[float, float],
    angle_rad: float = 0.0,
    samples: int = 72,
) -> np.ndarray:
    if samples < 8:
        raise ValueError("Use at least 8 perimeter samples.")
    a, b = axes
    t = np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False)
    local = np.column_stack([a * np.cos(t), b * np.sin(t)])
    return local @ _rotation_matrix(angle_rad).T + np.asarray(center, dtype=float)


def ellipse_pixel_confusion(
    soil_points2d: np.ndarray,
    center: tuple[float, float],
    axes: tuple[float, float],
    angle_rad: float = 0.0,
    soil_radius: float | None = None,
    grid_res: int = 120,
) -> dict[str, float]:
    """Compare a fitted ellipse against an observed 2D soil occupancy grid.

    A pixel is observed as soil if at least one soil point lands in that grid
    cell. The expected borehole void is the inside of the fitted ellipse.
    Therefore:
    - ``soil_inside_pixels`` are likely boundary leakage / false void errors.
    - ``void_outside_pixels`` are empty pixels outside the ellipse within the
      local soil-mass radius.
    """
    pts = np.asarray(soil_points2d, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("soil_points2d must have shape (N, 2).")
    if pts.shape[0] == 0:
        raise ValueError("At least one soil point is required.")
    if grid_res < 8:
        raise ValueError("grid_res must be at least 8.")

    cx, cy = center
    a, b = axes
    extent = max(a, b, soil_radius or 0.0)
    if extent <= 0:
        raise ValueError("Ellipse axes or soil_radius must define a positive extent.")
    if soil_radius is None:
        soil_radius = 1.75 * extent

    margin = max(0.1 * soil_radius, 1e-6)
    x = np.linspace(cx - soil_radius - margin, cx + soil_radius + margin, grid_res)
    y = np.linspace(cy - soil_radius - margin, cy + soil_radius + margin, grid_res)
    xx, yy = np.meshgrid(x, y, indexing="xy")
    grid_pts = np.column_stack([xx.ravel(), yy.ravel()])

    rel = grid_pts - np.array([cx, cy], dtype=float)
    soil_mass_mask = np.sum(rel * rel, axis=1) <= soil_radius * soil_radius
    inside_mask = ellipse_level_set(grid_pts, center, axes, angle_rad) <= 0.0

    x_edges = np.linspace(x.min(), x.max(), grid_res + 1)
    y_edges = np.linspace(y.min(), y.max(), grid_res + 1)
    H, _, _ = np.histogram2d(pts[:, 0], pts[:, 1], bins=[x_edges, y_edges])
    observed_soil = H.T.ravel() > 0

    valid = soil_mass_mask
    inside = inside_mask & valid
    outside = (~inside_mask) & valid
    soil_inside = observed_soil & inside
    void_inside = (~observed_soil) & inside
    soil_outside = observed_soil & outside
    void_outside = (~observed_soil) & outside

    inside_pixels = int(inside.sum())
    outside_pixels = int(outside.sum())
    total_pixels = inside_pixels + outside_pixels
    soil_inside_pixels = int(soil_inside.sum())
    void_outside_pixels = int(void_outside.sum())
    inside_void_rate = int(void_inside.sum()) / max(inside_pixels, 1)
    outside_soil_rate = int(soil_outside.sum()) / max(outside_pixels, 1)

    return {
        "soil_inside_pixels": soil_inside_pixels,
        "void_outside_pixels": void_outside_pixels,
        "inside_pixels": inside_pixels,
        "outside_pixels": outside_pixels,
        "total_pixels": total_pixels,
        "soil_inside_frac": soil_inside_pixels / max(inside_pixels, 1),
        "void_outside_frac": void_outside_pixels / max(outside_pixels, 1),
        "inside_void_rate": inside_void_rate,
        "outside_soil_rate": outside_soil_rate,
        "balanced_accuracy": 0.5 * (inside_void_rate + outside_soil_rate),
    }


def perimeter_completeness(
    candidates2d: np.ndarray,
    center: tuple[float, float],
    axes: tuple[float, float],
    angle_rad: float = 0.0,
    samples: int = 72,
    tolerance: float = 0.01,
) -> float:
    """Fraction of sampled ellipse perimeter with a nearby boundary candidate."""
    pts = np.asarray(candidates2d, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("candidates2d must have shape (N, 2).")
    if pts.shape[0] == 0:
        return 0.0
    if tolerance <= 0:
        raise ValueError("tolerance must be positive.")

    boundary = ellipse_boundary_points(center, axes, angle_rad, samples)
    deltas = boundary[:, None, :] - pts[None, :, :]
    nearest = np.sqrt(np.sum(deltas * deltas, axis=2)).min(axis=1)
    return float(np.mean(nearest <= tolerance))


def summarize_radius_continuity(radii: Iterable[float]) -> dict[str, float]:
    r = np.asarray(list(radii), dtype=float)
    if r.size < 2:
        return {
            "radius_diff_std": 0.0,
            "mean_abs_radius_jump": 0.0,
            "max_radius_jump": 0.0,
            "radius_roughness_cv": 0.0,
        }
    diffs = np.diff(r)
    mean_radius = max(float(np.mean(np.abs(r))), 1e-12)
    return {
        "radius_diff_std": float(np.std(diffs)),
        "mean_abs_radius_jump": float(np.mean(np.abs(diffs))),
        "max_radius_jump": float(np.max(np.abs(diffs))),
        "radius_roughness_cv": float(np.std(diffs) / mean_radius),
    }
