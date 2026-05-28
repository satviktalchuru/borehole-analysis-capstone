#!/usr/bin/env python3
"""Identify a borehole from HDD simulation data and export a fitted STL surface."""

from __future__ import annotations

import argparse
import csv
import inspect
import json
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.signal import savgol_filter
from scipy.spatial import cKDTree
from skimage.measure import EllipseModel, ransac
from sklearn.decomposition import PCA

from borehole_metrics import (
    ellipse_level_set,
    ellipse_pixel_confusion,
    perimeter_completeness,
    summarize_radius_continuity,
)


def normalize(v: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n >= eps else v * 0.0


def mirror_about_xz(points: np.ndarray) -> np.ndarray:
    mirrored = points.copy()
    mirrored[:, 1] *= -1.0
    return mirrored


def get_plane_basis(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = normalize(n)
    v = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(v, n)) > 0.9:
        v = np.array([0.0, 1.0, 0.0])
    e1 = normalize(np.cross(n, v))
    e2 = normalize(np.cross(n, e1))
    return e1, e2


def _rotate_vector(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    axis = normalize(axis)
    return (
        v * np.cos(angle)
        + np.cross(axis, v) * np.sin(angle)
        + axis * np.dot(axis, v) * (1.0 - np.cos(angle))
    )


def parallel_transport_frames(centers: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build low-twist cross-section frames along a fitted centerline."""
    if centers.shape[0] < 2:
        raise ValueError("At least two centers are required.")
    d = np.gradient(centers, axis=0)
    tangents = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    e1 = np.zeros_like(tangents)
    e2 = np.zeros_like(tangents)
    e1[0], e2[0] = get_plane_basis(tangents[0])

    for i in range(1, len(tangents)):
        prev_t = tangents[i - 1]
        curr_t = tangents[i]
        axis = np.cross(prev_t, curr_t)
        axis_norm = np.linalg.norm(axis)
        if axis_norm > 1e-10:
            angle = np.arctan2(axis_norm, np.clip(np.dot(prev_t, curr_t), -1.0, 1.0))
            transported = _rotate_vector(e1[i - 1], axis, angle)
        else:
            transported = e1[i - 1]
        e1[i] = normalize(transported - np.dot(transported, curr_t) * curr_t)
        if np.linalg.norm(e1[i]) < 1e-10:
            e1[i], _ = get_plane_basis(curr_t)
        e2[i] = normalize(np.cross(curr_t, e1[i]))
    return tangents, e1, e2


def gradient_boundary_mask(
    pts2d: np.ndarray,
    grid_res: int = 60,
    grad_thresh_pct: float = 70.0,
) -> np.ndarray:
    """Select points near high local 2D density gradients."""
    if pts2d.shape[0] < 20:
        return np.ones(pts2d.shape[0], dtype=bool)
    x, y = pts2d[:, 0], pts2d[:, 1]
    pad = 0.1 * max(x.max() - x.min(), y.max() - y.min(), 1e-6)
    H, xedges, yedges = np.histogram2d(
        x,
        y,
        bins=grid_res,
        range=[[x.min() - pad, x.max() + pad], [y.min() - pad, y.max() + pad]],
    )
    H_smooth = gaussian_filter(H, sigma=1.5)
    gx, gy = np.gradient(H_smooth)
    grad_mag = np.sqrt(gx * gx + gy * gy)
    thresh = np.percentile(grad_mag, grad_thresh_pct)
    boundary_grid = grad_mag > thresh
    xi = np.clip(np.digitize(x, xedges[:-1]) - 1, 0, grid_res - 1)
    yi = np.clip(np.digitize(y, yedges[:-1]) - 1, 0, grid_res - 1)
    return boundary_grid[xi, yi]


def radial_boundary_candidates(
    pts2d: np.ndarray,
    angle_bins: int = 72,
    min_bin_points: int = 4,
    quantile: float = 0.9,
) -> np.ndarray:
    """Select a robust radial envelope point from each angular bin."""
    if pts2d.shape[0] < max(angle_bins // 2, 12):
        return pts2d
    radii = np.linalg.norm(pts2d, axis=1)
    angles = (np.arctan2(pts2d[:, 1], pts2d[:, 0]) + 2.0 * np.pi) % (2.0 * np.pi)
    bin_ids = np.floor(angles / (2.0 * np.pi) * angle_bins).astype(int)
    bin_ids = np.clip(bin_ids, 0, angle_bins - 1)
    selected = []
    q = float(np.clip(quantile, 0.5, 1.0))
    for bin_id in range(angle_bins):
        idx = np.flatnonzero(bin_ids == bin_id)
        if idx.size < min_bin_points:
            continue
        target = np.quantile(radii[idx], q)
        chosen = idx[np.argmin(np.abs(radii[idx] - target))]
        selected.append(pts2d[chosen])
    if len(selected) < max(10, angle_bins // 4):
        return pts2d
    return np.asarray(selected, dtype=float)


def fit_circle_3pts(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, eps: float = 1e-12):
    (x1, y1), (x2, y2), (x3, y3) = p1, p2, p3
    A = np.array([[x2 - x1, y2 - y1], [x3 - x1, y3 - y1]], dtype=float)
    B = np.array(
        [
            0.5 * ((x2 * x2 - x1 * x1) + (y2 * y2 - y1 * y1)),
            0.5 * ((x3 * x3 - x1 * x1) + (y3 * y3 - y1 * y1)),
        ],
        dtype=float,
    )
    if abs(np.linalg.det(A)) < eps:
        return None
    cx, cy = np.linalg.solve(A, B)
    r = np.sqrt((cx - x1) ** 2 + (cy - y1) ** 2)
    return (cx, cy, r) if np.isfinite(r) and r > 0 else None


def ransac_circle(
    pts2d: np.ndarray,
    n_trials: int,
    tol: float,
    min_inlier_frac: float,
    rng: np.random.Generator,
):
    N = pts2d.shape[0]
    if N < 10:
        return None
    best_count, best_model, best_mask = 0, None, None
    for _ in range(n_trials):
        idx = rng.choice(N, size=3, replace=False)
        model = fit_circle_3pts(pts2d[idx[0]], pts2d[idx[1]], pts2d[idx[2]])
        if model is None:
            continue
        cx, cy, r = model
        resid = np.abs(np.sqrt((pts2d[:, 0] - cx) ** 2 + (pts2d[:, 1] - cy) ** 2) - r)
        mask = resid < tol
        count = int(mask.sum())
        if count > best_count:
            best_count, best_model, best_mask = count, model, mask
    if best_model is None or best_count / N < min_inlier_frac:
        return None
    cx, cy, r = best_model
    return {"kind": "circle", "cx": cx, "cy": cy, "a": r, "b": r, "theta": 0.0, "inliers": best_mask}


def fit_ransac_model(
    pts2d: np.ndarray,
    max_trials: int,
    tol: float,
    random_state: int,
) -> tuple[EllipseModel | None, np.ndarray]:
    kwargs = {
        "min_samples": 5,
        "residual_threshold": tol,
        "max_trials": max_trials,
    }
    if "rng" in inspect.signature(ransac).parameters:
        kwargs["rng"] = np.random.default_rng(random_state)
    else:
        kwargs["random_state"] = random_state
    return ransac(pts2d, EllipseModel, **kwargs)


def ellipse_model_parameters(model: EllipseModel) -> tuple[float, float, float, float, float]:
    if hasattr(model, "center") and hasattr(model, "axis_lengths") and hasattr(model, "theta"):
        cx, cy = model.center
        a, b = model.axis_lengths
        theta = model.theta
        return float(cx), float(cy), float(a), float(b), float(theta)
    if getattr(model, "params", None) is not None:
        cx, cy, a, b, theta = model.params
        return float(cx), float(cy), float(a), float(b), float(theta)
    raise ValueError("Unable to extract ellipse parameters from RANSAC model.")


def ransac_ellipse(
    pts2d: np.ndarray,
    tol: float,
    min_inlier_frac: float,
    max_axis_ratio: float,
    max_trials: int,
    random_state: int,
):
    if pts2d.shape[0] < 12:
        return None
    try:
        model, inliers = fit_ransac_model(pts2d, max_trials=max_trials, tol=tol, random_state=random_state)
    except (ValueError, np.linalg.LinAlgError):
        return None
    if model is None:
        return None
    cx, cy, a, b, theta = ellipse_model_parameters(model)
    if not np.all(np.isfinite([cx, cy, a, b, theta])) or a <= 0 or b <= 0:
        return None
    axis_ratio = max(a, b) / max(min(a, b), 1e-12)
    if axis_ratio > max_axis_ratio or inliers.sum() / len(inliers) < min_inlier_frac:
        return None
    return {"kind": "ellipse", "cx": cx, "cy": cy, "a": a, "b": b, "theta": theta, "inliers": inliers}


def dedupe_fit_candidates(candidates: list[dict], radius_tol: float = 0.002, center_tol: float = 0.004) -> list[dict]:
    unique = []
    for candidate in candidates:
        radius = _fit_radius(candidate)
        center = np.array([candidate["fit"]["cx"], candidate["fit"]["cy"]], dtype=float)
        is_duplicate = False
        for existing in unique:
            existing_radius = _fit_radius(existing)
            existing_center = np.array([existing["fit"]["cx"], existing["fit"]["cy"]], dtype=float)
            if abs(radius - existing_radius) <= radius_tol and np.linalg.norm(center - existing_center) <= center_tol:
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(candidate)
    return unique


def evaluate_fit_candidate(
    fit: dict,
    pts2d: np.ndarray,
    candidates: np.ndarray,
    slice_index: int,
    station: float,
    aspect: float,
    fit_tol: float,
    soil_radius_factor: float,
    pixel_grid_res: int,
) -> dict:
    cx, cy, a, b, theta = fit["cx"], fit["cy"], fit["a"], fit["b"], fit["theta"]
    inliers = fit["inliers"]
    inlier_ratio = float(inliers.sum() / max(candidates.shape[0], 1))
    equivalent_radius = float(np.sqrt(a * b))
    soil_radius = soil_radius_factor * max(a, b)
    pixel_metrics = ellipse_pixel_confusion(
        pts2d,
        center=(cx, cy),
        axes=(a, b),
        angle_rad=theta,
        soil_radius=soil_radius,
        grid_res=pixel_grid_res,
    )
    inside_soil_mask = ellipse_level_set(pts2d, (cx, cy), (a, b), theta) <= 0.0
    soil_inside_points = int(inside_soil_mask.sum())
    soil_inside_point_frac = float(soil_inside_points / max(pts2d.shape[0], 1))
    completeness = perimeter_completeness(
        candidates,
        center=(cx, cy),
        axes=(a, b),
        angle_rad=theta,
        samples=72,
        tolerance=fit_tol * 3.0,
    )
    cavity_quality = inlier_ratio * completeness * (1.0 - soil_inside_point_frac)
    row = {
        "slice_index": slice_index,
        "station": float(station),
        "cx": float(cx),
        "cy": float(cy),
        "axis_a": float(a),
        "axis_b": float(b),
        "theta": float(theta),
        "equivalent_radius": equivalent_radius,
        "candidate_aspect": aspect,
        "inlier_ratio": inlier_ratio,
        "perimeter_completeness": completeness,
        "soil_inside_points": soil_inside_points,
        "soil_inside_point_frac": soil_inside_point_frac,
        "soil_inside_pixels": pixel_metrics["soil_inside_pixels"],
        "void_outside_pixels": pixel_metrics["void_outside_pixels"],
        "soil_inside_frac": pixel_metrics["soil_inside_frac"],
        "void_outside_frac": pixel_metrics["void_outside_frac"],
        "balanced_accuracy": pixel_metrics["balanced_accuracy"],
        "cavity_quality": float(cavity_quality),
    }
    return {"fit": fit, "row": row}


def ransac_fit_candidates(
    pts2d: np.ndarray,
    boundary_candidates: np.ndarray,
    model: str,
    aspect: float,
    slice_index: int,
    station: float,
    fit_tol: float,
    min_inlier_frac: float,
    max_axis_ratio: float,
    ransac_trials: int,
    seed: int,
    rng: np.random.Generator,
    candidate_count: int,
    candidate_attempts: int,
    soil_radius_factor: float,
    pixel_grid_res: int,
) -> list[dict]:
    evaluated = []
    attempts = max(candidate_attempts or candidate_count, candidate_count, 1)
    for attempt in range(attempts):
        if model == "ellipse":
            fit = ransac_ellipse(
                boundary_candidates,
                fit_tol,
                min_inlier_frac,
                max_axis_ratio,
                ransac_trials,
                seed + attempt,
            )
        else:
            fit = ransac_circle(boundary_candidates, ransac_trials, fit_tol, min_inlier_frac, rng)
        if fit is None:
            continue
        evaluated.append(
            evaluate_fit_candidate(
                fit,
                pts2d,
                boundary_candidates,
                slice_index,
                station,
                aspect,
                fit_tol,
                soil_radius_factor,
                pixel_grid_res,
            )
        )
    evaluated.sort(key=lambda item: item["row"]["cavity_quality"], reverse=True)
    return dedupe_fit_candidates(evaluated)[:candidate_count]


def ring_3d(
    c: np.ndarray,
    e1: np.ndarray,
    e2: np.ndarray,
    cx: float,
    cy: float,
    a: float,
    b: float,
    theta: float,
    n: int,
) -> np.ndarray:
    t = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    local = np.column_stack([a * np.cos(t), b * np.sin(t)])
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    xy = local @ rot.T + np.array([cx, cy])
    return c + xy[:, 0, None] * e1 + xy[:, 1, None] * e2


def loft_rings_to_mesh(rings3d: list[np.ndarray]) -> trimesh.Trimesh:
    n = rings3d[0].shape[0]
    verts = np.vstack(rings3d)
    faces = []
    for i in range(len(rings3d) - 1):
        for j in range(n):
            a0, a1 = i * n + j, i * n + ((j + 1) % n)
            b0, b1 = (i + 1) * n + j, (i + 1) * n + ((j + 1) % n)
            faces.append([a0, b0, a1])
            faces.append([a1, b0, b1])
    start_center = len(verts)
    end_center = start_center + 1
    verts = np.vstack([verts, rings3d[0].mean(axis=0), rings3d[-1].mean(axis=0)])
    end_offset = (len(rings3d) - 1) * n
    for j in range(n):
        next_j = (j + 1) % n
        faces.append([start_center, next_j, j])
        faces.append([end_center, end_offset + j, end_offset + next_j])
    return trimesh.Trimesh(np.asarray(verts), np.asarray(faces, dtype=np.int64), process=False)


def candidate_aspect_ratio(points2d: np.ndarray) -> float:
    if points2d.shape[0] < 5:
        return 1.0
    eigs = np.linalg.eigvalsh(np.cov(points2d.T))
    eigs = np.sort(np.abs(eigs))[::-1]
    return float(np.sqrt(eigs[0] / max(eigs[1], 1e-12)))


def smooth_odd_window(count: int, requested: int) -> int:
    window = min(requested, count if count % 2 == 1 else count - 1)
    return max(window, 3)


def _fill_outliers(values: np.ndarray, keep_mask: np.ndarray) -> np.ndarray:
    x = np.arange(values.size)
    if keep_mask.sum() == 0:
        return values
    if keep_mask.sum() == 1:
        return np.full_like(values, values[keep_mask][0])
    return np.interp(x, x[keep_mask], values[keep_mask])


def regularize_slice_fits(
    fits: list[dict],
    circularity_prior: float = 0.7,
    outlier_mad: float = 4.0,
    window_size: int = 13,
) -> tuple[dict[str, np.ndarray], int]:
    """Smooth slice parameters and remove isolated RANSAC radius spikes."""
    if not fits:
        raise ValueError("At least one fit is required.")
    cx = np.asarray([f["fit"]["cx"] for f in fits], dtype=float)
    cy = np.asarray([f["fit"]["cy"] for f in fits], dtype=float)
    axis_a = np.asarray([f["fit"]["a"] for f in fits], dtype=float)
    axis_b = np.asarray([f["fit"]["b"] for f in fits], dtype=float)
    theta = np.unwrap(np.asarray([f["fit"]["theta"] for f in fits], dtype=float))
    equiv = np.sqrt(np.maximum(axis_a * axis_b, 1e-12))

    if len(fits) >= 5:
        median = np.median(equiv)
        mad = np.median(np.abs(equiv - median))
        if mad > 1e-12:
            keep = np.abs(equiv - median) <= outlier_mad * 1.4826 * mad
        else:
            keep = np.ones_like(equiv, dtype=bool)
    else:
        keep = np.ones_like(equiv, dtype=bool)

    rejected = int((~keep).sum())
    cx = _fill_outliers(cx, keep)
    cy = _fill_outliers(cy, keep)
    axis_a = _fill_outliers(axis_a, keep)
    axis_b = _fill_outliers(axis_b, keep)
    theta = _fill_outliers(theta, keep)
    equiv = np.sqrt(np.maximum(axis_a * axis_b, 1e-12))

    prior = float(np.clip(circularity_prior, 0.0, 1.0))
    axis_a = (1.0 - prior) * axis_a + prior * equiv
    axis_b = (1.0 - prior) * axis_b + prior * equiv

    if len(fits) >= 5:
        window = smooth_odd_window(len(fits), window_size)
        poly = min(2, window - 1)
        cx = savgol_filter(cx, window, poly)
        cy = savgol_filter(cy, window, poly)
        axis_a = savgol_filter(axis_a, window, poly)
        axis_b = savgol_filter(axis_b, window, poly)
        theta = savgol_filter(theta, window, poly)

    axis_a = np.maximum(axis_a, 1e-6)
    axis_b = np.maximum(axis_b, 1e-6)
    return {
        "cx": cx,
        "cy": cy,
        "axis_a": axis_a,
        "axis_b": axis_b,
        "theta": theta,
        "equivalent_radius": np.sqrt(axis_a * axis_b),
    }, rejected


def _fit_radius(candidate: dict) -> float:
    if "equivalent_radius" in candidate.get("row", {}):
        return float(candidate["row"]["equivalent_radius"])
    fit = candidate["fit"]
    return float(np.sqrt(max(fit["a"] * fit["b"], 1e-12)))


def fit_transition_cost(prev: dict, curr: dict) -> float:
    prev_fit = prev["fit"]
    curr_fit = curr["fit"]
    prev_r = _fit_radius(prev)
    curr_r = _fit_radius(curr)
    scale = max(0.5 * (prev_r + curr_r), 1e-6)
    radius_cost = ((curr_r - prev_r) / scale) ** 2
    center_cost = (
        ((curr_fit["cx"] - prev_fit["cx"]) / scale) ** 2
        + ((curr_fit["cy"] - prev_fit["cy"]) / scale) ** 2
    )
    axis_ratio_prev = max(prev_fit["a"], prev_fit["b"]) / max(min(prev_fit["a"], prev_fit["b"]), 1e-12)
    axis_ratio_curr = max(curr_fit["a"], curr_fit["b"]) / max(min(curr_fit["a"], curr_fit["b"]), 1e-12)
    axis_cost = (np.log(axis_ratio_curr) - np.log(axis_ratio_prev)) ** 2
    theta_delta = np.arctan2(np.sin(curr_fit["theta"] - prev_fit["theta"]), np.cos(curr_fit["theta"] - prev_fit["theta"]))
    theta_cost = 0.05 * theta_delta * theta_delta
    return float(radius_cost + 0.35 * center_cost + 0.25 * axis_cost + theta_cost)


def choose_global_fit_sequence(
    slice_candidates: list[list[dict]],
    smoothness_weight: float = 2.5,
) -> list[dict]:
    """Choose a high-quality, physically smooth RANSAC candidate path."""
    if not slice_candidates:
        return []
    if any(len(candidates) == 0 for candidates in slice_candidates):
        raise ValueError("Each slice must provide at least one candidate fit.")

    costs: list[np.ndarray] = []
    parents: list[np.ndarray] = []
    first = np.asarray([-float(c["row"].get("cavity_quality", 0.0)) for c in slice_candidates[0]], dtype=float)
    costs.append(first)
    parents.append(np.full(first.shape, -1, dtype=int))

    for i in range(1, len(slice_candidates)):
        prev_candidates = slice_candidates[i - 1]
        curr_candidates = slice_candidates[i]
        curr_cost = np.full(len(curr_candidates), np.inf, dtype=float)
        curr_parent = np.full(len(curr_candidates), -1, dtype=int)
        for j, curr in enumerate(curr_candidates):
            quality_cost = -float(curr["row"].get("cavity_quality", 0.0))
            for k, prev in enumerate(prev_candidates):
                transition = smoothness_weight * fit_transition_cost(prev, curr)
                total = costs[i - 1][k] + quality_cost + transition
                if total < curr_cost[j]:
                    curr_cost[j] = total
                    curr_parent[j] = k
        costs.append(curr_cost)
        parents.append(curr_parent)

    selected_idxs = [int(np.argmin(costs[-1]))]
    for i in range(len(slice_candidates) - 1, 0, -1):
        selected_idxs.append(int(parents[i][selected_idxs[-1]]))
    selected_idxs.reverse()
    return [slice_candidates[i][idx] for i, idx in enumerate(selected_idxs)]


def write_slice_csv(path: Path, rows: list[dict[str, float]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vtk", default="/Users/satviktalchuru/Desktop/prestress2800000.vtk")
    parser.add_argument("--tool-stl", default="/Users/satviktalchuru/Desktop/drillhead2800000.stl")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--out-stl", default="borehole_final_smooth.stl")
    parser.add_argument("--model", choices=["ellipse", "circle"], default="ellipse")
    parser.add_argument("--mirror-xz", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dist-thresh", type=float, default=0.12)
    parser.add_argument("--step-along", type=float, default=0.01)
    parser.add_argument("--slab-half-thick", type=float, default=0.02)
    parser.add_argument("--min-slice-pts", type=int, default=20)
    parser.add_argument("--ball-r", type=float, default=0.06)
    parser.add_argument("--grad-grid-res", type=int, default=60)
    parser.add_argument("--grad-thresh-pct", type=float, default=70.0)
    parser.add_argument("--boundary-mode", choices=["gradient", "radial", "hybrid"], default="gradient")
    parser.add_argument("--radial-angle-bins", type=int, default=72)
    parser.add_argument("--radial-quantile", type=float, default=0.9)
    parser.add_argument("--max-aspect-ratio", type=float, default=5.0)
    parser.add_argument("--ransac-trials", type=int, default=180)
    parser.add_argument("--ransac-candidates", type=int, default=5)
    parser.add_argument("--ransac-candidate-attempts", type=int, default=0)
    parser.add_argument("--path-smoothness-weight", type=float, default=2.5)
    parser.add_argument("--fit-tol", type=float, default=0.008)
    parser.add_argument("--min-inlier-frac", type=float, default=0.45)
    parser.add_argument("--ring-n", type=int, default=64)
    parser.add_argument("--soil-radius-factor", type=float, default=2.5)
    parser.add_argument("--pixel-grid-res", type=int, default=120)
    parser.add_argument("--circularity-prior", type=float, default=0.75)
    parser.add_argument("--radius-outlier-mad", type=float, default=4.0)
    parser.add_argument("--smooth-window", type=int, default=15)
    parser.add_argument("--max-hole-points", type=int, default=250_000)
    parser.add_argument("--max-centerline-slices", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    soil = pv.read(args.vtk)
    points = np.asarray(soil.points)
    tool = trimesh.load_mesh(args.tool_stl)
    tool_pts = np.asarray(tool.vertices)
    print("Soil points:", points.shape)
    print("Tool vertices:", tool_pts.shape)

    if args.mirror_xz:
        points = np.vstack([points, mirror_about_xz(points)])
        print("After mirroring:", points.shape)

    tool_tree = cKDTree(tool_pts)
    dists, _ = tool_tree.query(points, k=1)
    hole_pts = points[dists < args.dist_thresh]
    if hole_pts.shape[0] > args.max_hole_points:
        hole_pts = hole_pts[rng.choice(hole_pts.shape[0], args.max_hole_points, replace=False)]
    print("Hole candidate points:", hole_pts.shape)
    if hole_pts.shape[0] < 1000:
        raise RuntimeError("Very few near-tool points. Increase --dist-thresh.")

    pca = PCA(3).fit(hole_pts)
    main_dir = normalize(pca.components_[0])
    center0 = hole_pts.mean(axis=0)
    proj = (hole_pts - center0) @ main_dir
    stations = np.arange(proj.min(), proj.max(), args.step_along)

    centers = []
    station_vals = []
    half = args.step_along / 2.0
    for s in stations:
        chunk = hole_pts[np.abs(proj - s) < half]
        if chunk.shape[0] >= args.min_slice_pts:
            centers.append(chunk.mean(axis=0))
            station_vals.append(s)
    centers = np.asarray(centers)
    station_vals = np.asarray(station_vals)
    if args.max_centerline_slices and centers.shape[0] > args.max_centerline_slices:
        sel = np.linspace(0, centers.shape[0] - 1, args.max_centerline_slices).round().astype(int)
        centers = centers[sel]
        station_vals = station_vals[sel]
    print("Centerline raw points:", centers.shape)

    centers_smooth = gaussian_filter1d(centers, sigma=2.5, axis=0)
    tangents, frame_e1, frame_e2 = parallel_transport_frames(centers_smooth)

    hole_tree = cKDTree(hole_pts)
    slice_candidate_sets = []
    rejected_shape = 0
    rejected_fit = 0
    skipped_neighborhood = 0
    skipped_slab = 0
    analyzed_slices = 0

    for i, c in enumerate(centers_smooth):
        n = tangents[i]
        e1, e2 = frame_e1[i], frame_e2[i]
        slab = args.slab_half_thick * (2.0 if i < 5 or i >= len(centers_smooth) - 5 else 1.0)
        idxs = hole_tree.query_ball_point(c, r=args.ball_r)
        if len(idxs) < args.min_slice_pts:
            skipped_neighborhood += 1
            continue
        local = hole_pts[idxs]
        rel = local - c
        local = local[np.abs(rel @ n) < slab]
        if local.shape[0] < args.min_slice_pts:
            skipped_slab += 1
            continue
        analyzed_slices += 1
        rel2 = local - c
        pts2d = np.column_stack([rel2 @ e1, rel2 @ e2])

        grad_candidates = pts2d[gradient_boundary_mask(pts2d, args.grad_grid_res, args.grad_thresh_pct)]
        radial_candidates = radial_boundary_candidates(
            pts2d,
            angle_bins=args.radial_angle_bins,
            quantile=args.radial_quantile,
        )
        if args.boundary_mode == "gradient":
            candidates = grad_candidates
        elif args.boundary_mode == "radial":
            candidates = radial_candidates
        else:
            candidates = np.vstack([grad_candidates, radial_candidates])
        if candidates.shape[0] < 10:
            candidates = pts2d
        if candidates.shape[0] > 600:
            candidates = candidates[rng.choice(candidates.shape[0], 600, replace=False)]

        aspect = candidate_aspect_ratio(candidates)
        if aspect > args.max_aspect_ratio:
            rejected_shape += 1
            continue

        fit_candidates = ransac_fit_candidates(
            pts2d,
            candidates,
            args.model,
            aspect,
            i,
            station_vals[i],
            args.fit_tol,
            args.min_inlier_frac,
            args.max_aspect_ratio,
            args.ransac_trials,
            args.seed + i * max(args.ransac_candidates * 3, 1),
            rng,
            args.ransac_candidates,
            args.ransac_candidate_attempts,
            args.soil_radius_factor,
            args.pixel_grid_res,
        )
        if not fit_candidates:
            rejected_fit += 1
            continue

        for candidate in fit_candidates:
            candidate["i"] = i
            candidate["center"] = c
            candidate["normal"] = n
        slice_candidate_sets.append(fit_candidates)

    if len(slice_candidate_sets) < 3:
        raise RuntimeError("Not enough successful fits to loft a surface.")
    fits = choose_global_fit_sequence(slice_candidate_sets, smoothness_weight=args.path_smoothness_weight)
    slice_rows = [f["row"] for f in fits]

    centers_fit = np.asarray([f["center"] for f in fits])
    raw_centers_fit = centers_fit.copy()
    params, regularized_outlier_slices = regularize_slice_fits(
        fits,
        circularity_prior=args.circularity_prior,
        outlier_mad=args.radius_outlier_mad,
        window_size=args.smooth_window,
    )
    fit_tangents, fit_e1, fit_e2 = parallel_transport_frames(raw_centers_fit)
    centers_fit = raw_centers_fit + params["cx"][:, None] * fit_e1 + params["cy"][:, None] * fit_e2
    centers_fit_smooth = gaussian_filter1d(centers_fit, sigma=2.5, axis=0)
    tangents_smooth, ring_e1, ring_e2 = parallel_transport_frames(centers_fit_smooth)

    axes_a = np.asarray([f["row"]["axis_a"] for f in fits])
    axes_b = np.asarray([f["row"]["axis_b"] for f in fits])
    equiv_r = np.asarray([f["row"]["equivalent_radius"] for f in fits])
    axes_a_smooth = params["axis_a"]
    axes_b_smooth = params["axis_b"]
    theta_smooth = params["theta"]
    equiv_r_regularized = params["equivalent_radius"]

    for k, f in enumerate(fits):
        row = f["row"]
        row["regularized_cx"] = float(params["cx"][k])
        row["regularized_cy"] = float(params["cy"][k])
        row["regularized_axis_a"] = float(axes_a_smooth[k])
        row["regularized_axis_b"] = float(axes_b_smooth[k])
        row["regularized_theta"] = float(theta_smooth[k])
        row["regularized_equivalent_radius"] = float(equiv_r_regularized[k])

    rings = []
    for k, f in enumerate(fits):
        c = centers_fit_smooth[k]
        e1, e2 = ring_e1[k], ring_e2[k]
        rings.append(
            ring_3d(
                c,
                e1,
                e2,
                0.0,
                0.0,
                max(float(axes_a_smooth[k]), 1e-6),
                max(float(axes_b_smooth[k]), 1e-6),
                float(theta_smooth[k]),
                args.ring_n,
            )
        )

    mesh = loft_rings_to_mesh(rings)
    stl_path = out_dir / args.out_stl
    mesh.export(stl_path)
    write_slice_csv(out_dir / "borehole_slice_metrics.csv", slice_rows)

    continuity = summarize_radius_continuity(equiv_r_regularized)
    d1 = np.gradient(centers_fit_smooth, axis=0)
    d2 = np.gradient(d1, axis=0)
    curvature = np.linalg.norm(d2, axis=1)
    summary = {
        "model": args.model,
        "boundary_mode": args.boundary_mode,
        "radial_angle_bins": int(args.radial_angle_bins),
        "radial_quantile": float(args.radial_quantile),
        "circularity_prior": float(args.circularity_prior),
        "ransac_candidates": int(args.ransac_candidates),
        "path_smoothness_weight": float(args.path_smoothness_weight),
        "regularized_radius_outliers": int(regularized_outlier_slices),
        "total_centerline_slices": int(len(centers_smooth)),
        "accepted_slices": int(len(fits)),
        "analyzed_slices": int(analyzed_slices),
        "skipped_neighborhood_slices": int(skipped_neighborhood),
        "skipped_slab_slices": int(skipped_slab),
        "rejected_elongated_slices": int(rejected_shape),
        "ransac_failures": int(rejected_fit),
        "slice_success_rate": float(len(fits) / max(len(centers_smooth), 1)),
        "slice_analysis_rate": float(analyzed_slices / max(len(centers_smooth), 1)),
        "fit_success_of_analyzed_rate": float(len(fits) / max(analyzed_slices, 1)),
        "mean_inlier_ratio": float(np.mean([r["inlier_ratio"] for r in slice_rows])),
        "mean_perimeter_completeness": float(np.mean([r["perimeter_completeness"] for r in slice_rows])),
        "mean_soil_inside_points": float(np.mean([r["soil_inside_points"] for r in slice_rows])),
        "mean_soil_inside_point_frac": float(np.mean([r["soil_inside_point_frac"] for r in slice_rows])),
        "mean_balanced_accuracy": float(np.mean([r["balanced_accuracy"] for r in slice_rows])),
        "mean_soil_inside_pixels": float(np.mean([r["soil_inside_pixels"] for r in slice_rows])),
        "mean_void_outside_pixels": float(np.mean([r["void_outside_pixels"] for r in slice_rows])),
        "mean_cavity_quality": float(np.mean([r["cavity_quality"] for r in slice_rows])),
        "mean_curvature": float(np.mean(curvature)),
        "max_curvature": float(np.max(curvature)),
        **continuity,
        "stl": str(stl_path),
        "slice_metrics_csv": str(out_dir / "borehole_slice_metrics.csv"),
    }
    with (out_dir / "borehole_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    if not args.no_plots:
        import matplotlib.pyplot as plt

        radius_plot_path = out_dir / "radius_continuity.png"
        quality_plot_path = out_dir / "slice_quality.png"

        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(equiv_r, alpha=0.45, label="equivalent radius")
        ax.plot(equiv_r_regularized, linewidth=2, label="regularized")
        ax.set_xlabel("Accepted slice")
        ax.set_ylabel("Equivalent radius")
        ax.set_title("Borehole Radius Continuity")
        ax.grid(True)
        ax.legend()
        fig.tight_layout()
        fig.savefig(radius_plot_path, dpi=180)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot([r["cavity_quality"] for r in slice_rows], label="cavity quality")
        ax.plot([r["balanced_accuracy"] for r in slice_rows], label="pixel balanced accuracy")
        ax.set_xlabel("Accepted slice")
        ax.set_ylim(0, 1.05)
        ax.grid(True)
        ax.legend()
        fig.tight_layout()
        fig.savefig(quality_plot_path, dpi=180)
        plt.close(fig)

        print(f"Saved radius plot: {radius_plot_path}")
        print(f"Saved quality plot: {quality_plot_path}")

    print("===== FINAL RECONSTRUCTION SUMMARY =====")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
