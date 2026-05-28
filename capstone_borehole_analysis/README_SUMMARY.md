# Borehole Surface Reconstruction Summary

## Project Goal

Identify the long borehole in a simulated horizontal directional drilling data set, fit a piecewise surface to the borehole boundary, and export the reconstructed borehole surface as an STL file for CAD/engineering use.

## Input Data Used

- Soil point cloud: `/Users/satviktalchuru/Desktop/prestress2800000.vtk`
- Drill/tool geometry: `/Users/satviktalchuru/Desktop/drillhead2800000.stl`

## Final Output Files

- `outputs/borehole_final_smooth.stl`
  - Final lofted borehole surface.
- `outputs/borehole_slice_metrics.csv`
  - Per-slice fit and quality metrics.
- `outputs/borehole_summary.json`
  - Overall reconstruction summary and aggregate metrics.

## Algorithm Implemented

1. Load the VTK soil point cloud and STL drillhead geometry.
2. Mirror the soil points about the XZ plane to reconstruct symmetry.
3. Select likely borehole-region soil points by querying distance to the drillhead mesh.
4. Estimate the borehole centerline using PCA and slice the candidate points along the main borehole direction.
5. For each slice:
   - Extract local slab points around the centerline station.
   - Project the local 3D points into a 2D cross-section plane.
   - Build a 2D density map.
   - Compute density-gradient magnitude.
   - Keep high-gradient candidate points near the void-soil boundary.
   - Reject overly elongated candidate clouds if needed.
   - Fit an ellipse using RANSAC.
   - Compute per-slice quality metrics.
6. Smooth the fitted centerline and ellipse radii.
7. Loft the fitted rings into a continuous surface mesh.
8. Export the final surface as STL.

## Improvements Added

- Gradient-based boundary candidate selection instead of fitting against all nearby soil points.
- Ellipse fitting option for cross-sections instead of forcing only circular geometry.
- Slice accounting to report how much of the borehole was actually analyzed.
- Pixel-based boundary metrics:
  - Soil pixels inside fitted ellipse.
  - Void pixels outside fitted ellipse within a local soil mass radius.
- Point-based leakage metric:
  - Soil points inside the fitted ellipse.
- Inlier ratio using the actual candidate boundary set.
- Perimeter completeness metric to measure boundary continuity.
- Radius continuity metrics to measure smoothness along the borehole.
- Final STL, CSV, and JSON export.

## Final Run Metrics

These numbers came from running:

```bash
.venv/bin/python borehole_piecewise_surface.py \
  --vtk /Users/satviktalchuru/Desktop/prestress2800000.vtk \
  --tool-stl /Users/satviktalchuru/Desktop/drillhead2800000.stl \
  --no-plots \
  --ransac-trials 50 \
  --pixel-grid-res 80 \
  --out-dir outputs
```

### Slice Coverage

- Total centerline slices generated: `132`
- Slices actually analyzed: `132`
- Slices skipped for too few neighborhood points: `0`
- Slices skipped for too few slab points: `0`
- Slices rejected as elongated: `0`
- RANSAC failures: `0`
- Accepted fitted slices: `132`

### Percent Analyzed

```text
132 analyzed / 132 total = 100%
```

### Percent Successfully Fit

```text
132 accepted / 132 analyzed = 100%
```

## Aggregate Quality Metrics

- Mean inlier ratio: `0.6351`
- Mean perimeter completeness: `1.0000`
- Mean soil-inside points: `3455.02`
- Mean soil-inside point fraction: `0.8044`
- Mean soil-inside pixels: `418.17`
- Mean void-outside pixels: `3457.99`
- Mean cavity quality score: `0.1223`
- Mean curvature: `0.000229`
- Max curvature: `0.001776`
- Radius difference standard deviation: `0.002786`
- Mean absolute radius jump: `0.001642`
- Max radius jump: `0.014577`
- Radius roughness coefficient of variation: `0.06042`

## Metric Interpretations

- `inlier_ratio`
  - Fraction of gradient-selected boundary candidates that agree with the RANSAC ellipse.
- `perimeter_completeness`
  - Fraction of sampled ellipse perimeter locations that have a nearby boundary candidate.
- `soil_inside_points`
  - Number of actual soil sample points lying inside the fitted ellipse for that slice. This is useful as a leakage / false-void indicator.
- `soil_inside_pixels`
  - Number of occupied soil grid cells inside the fitted ellipse.
- `void_outside_pixels`
  - Number of empty grid cells outside the ellipse but still inside the local projected soil-mass radius.
- `cavity_quality`
  - Composite score: inlier agreement times perimeter completeness times penalty for soil points inside the fitted ellipse.
- `radius_roughness_cv`
  - Continuity measure for the borehole radius along the fitted path. Lower is smoother.

## Important Note

PyVista prints a warning while reading the VTK file:

```text
Unsupported point attribute type
```

The script still reads the coordinate points and completes the full reconstruction. The warning appears to come from an unsupported or malformed point attribute in the ASCII VTK file, not from the geometry coordinates used by the model.

## How To Re-run

From `/Users/satviktalchuru/Documents/New project 3`:

```bash
.venv/bin/python borehole_piecewise_surface.py \
  --vtk /Users/satviktalchuru/Desktop/prestress2800000.vtk \
  --tool-stl /Users/satviktalchuru/Desktop/drillhead2800000.stl \
  --no-plots \
  --ransac-trials 50 \
  --pixel-grid-res 80 \
  --out-dir outputs
```

To run tests:

```bash
.venv/bin/python -m unittest tests/test_borehole_metrics.py
```

## Interactive 3D Viewer

The `viewer-react/` app provides a browser-based Three.js viewer for the
generated STL mesh and reconstruction metrics.

For local development:

```bash
cd viewer-react
npm install
npm run dev
```

Then open the local Vite URL, usually:

```text
http://127.0.0.1:5173/
```

For a production-equivalent local preview:

```bash
npm test
npm run build
npm run preview
```

Public users should access a deployed static build, not the Vite development
server. See `docs/deployment.md` for Vercel deployment instructions.

## Model Evaluation

Generate a cross-run reconstruction comparison:

```bash
python borehole_evaluation.py \
  --run 2800000-dp outputs \
  --run 2750000-single outputs_2750000 \
  --run 2750000-dp outputs_2750000_dp \
  --run 2750000-hybrid-dp outputs_2750000_hybrid_dp \
  --out-dir docs
```

This writes:

- `docs/model_evaluation.md`
- `docs/model_evaluation.csv`
