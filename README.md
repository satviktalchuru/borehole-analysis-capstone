# Borehole Analysis Capstone

UCSB Data Science year-long capstone project for reconstructing horizontal directional drilling borehole geometry from noisy 3D simulation data.

The short version: this project turns raw, hard-to-interpret simulation particles into a continuous 3D borehole mesh that can be inspected in a browser, evaluated with quality metrics, and exported as a CAD-ready STL file.

## Why This Matters

Horizontal directional drilling (HDD) is used to install underground utilities without digging a full trench. In simulation, the drilling process produces large 3D point clouds showing soil particles, tool geometry, and the resulting cavity.

The challenge is that the borehole is not given as a clean surface. It has to be inferred from noisy, irregular particle data. Raw simulation output can contain hundreds of thousands of points, gaps, outliers, partial boundaries, and changing cross-sections. That makes it difficult for an engineer or researcher to answer simple questions:

- Where is the borehole?
- How continuous is the cavity?
- Is the reconstructed surface smooth or physically plausible?
- Can the geometry be exported into standard 3D/CAD formats?

This project builds a reconstruction pipeline for that problem.

## What The Project Does

The pipeline takes simulation files such as:

- `.vtk` soil particle data
- `.stl` drillhead/tool geometry

and produces:

- a watertight reconstructed borehole mesh: `borehole_final_smooth.stl`
- per-slice reconstruction metrics: `borehole_slice_metrics.csv`
- summary quality metrics: `borehole_summary.json`
- an interactive React/Three.js mesh viewer

The main implementation lives in [`capstone_borehole_analysis/`](capstone_borehole_analysis/).

## What We Tried Before

Early versions treated the reconstruction as a simpler geometry-fitting problem: slice the point cloud, fit one ellipse or circle per slice, and connect those slices into a mesh.

That worked on clean regions, but it produced visible artifacts:

- neighboring slices could choose inconsistent fits
- sparse regions created jagged transitions
- some slices latched onto noise instead of the cavity boundary
- the resulting STL could look spliced or uneven

The key lesson was that each slice cannot be treated as an isolated problem. A real borehole should be locally smooth and continuous, so the model needs both local fit quality and global path consistency.

## Final Approach

The current pipeline combines computational geometry, robust statistical fitting, and scientific Python tooling.

### 1. Find The Borehole Region

The code loads the VTK point cloud and STL drillhead geometry, then uses spatial queries to identify points near the drilled region. KD-tree style spatial indexing keeps this efficient for large point clouds.

### 2. Estimate The Centerline With PCA

Principal Component Analysis (PCA) estimates the main axis of the borehole. This gives the pipeline a coordinate system for slicing the point cloud along the likely drilling direction.

### 3. Slice The Point Cloud

The candidate points are divided into many thin cross-sections along the centerline. Each slice becomes a smaller 2D boundary-detection problem.

### 4. Detect Boundary Candidates

Instead of fitting against every point in a slice, the pipeline looks for likely cavity-boundary points. It supports:

- gradient-based boundary detection from local density maps
- radial boundary extraction from angular bins
- hybrid gradient/radial extraction

This helps separate meaningful borehole boundary evidence from interior noise and unrelated soil points.

### 5. Fit Ellipses With RANSAC

Each slice is fit with RANSAC ellipse estimation. RANSAC is useful here because it can tolerate outliers: it repeatedly proposes candidate fits and keeps the one that best agrees with the boundary evidence.

### 6. Choose Fits Globally

The strongest upgrade is dynamic-programming fit selection. Rather than accepting the best RANSAC fit in each slice independently, the pipeline can keep multiple candidate fits per slice and choose the best sequence across the whole borehole.

That sequence is scored by:

- local fit quality
- smoothness between neighboring slices
- radius continuity
- physically plausible geometry

This reduces splicing artifacts and makes the final borehole surface more stable.

### 7. Smooth And Export A Mesh

The selected slice fits are smoothed, converted into rings, lofted into a continuous surface, capped, and exported as a watertight STL mesh.

## Results

The evaluation report compares several reconstruction runs:

| Run | Accepted Slices | Watertight | Components | Cavity Quality | Roughness CV |
|---|---:|:---:|---:|---:|---:|
| `2800000-dp` | 132/132 | yes | 1 | 0.1260 | 0.0138 |
| `2750000-single` | 137/137 | yes | 1 | 0.1389 | 0.0131 |
| `2750000-dp` | 137/137 | yes | 1 | 0.1579 | 0.0132 |
| `2750000-hybrid-dp` | 137/137 | yes | 1 | 0.1463 | 0.0154 |

The dynamic-programming version improved fit quality while keeping the mesh watertight and smooth. The radial/hybrid experiment was implemented and tested, but gradient + dynamic programming remains the default because it performed better on the available datasets.

Full evaluation: [`capstone_borehole_analysis/docs/model_evaluation.md`](capstone_borehole_analysis/docs/model_evaluation.md)

## Interactive Viewer

The project includes a React/Three.js viewer for inspecting the reconstructed STL mesh. It can display the mesh normally or color it by per-slice cavity quality, making weak reconstruction regions easier to spot.

Viewer source:

```text
capstone_borehole_analysis/viewer-react/
```

Production deployment is configured through Vercel. Public users should access the built static site, not a local Vite development server.

Deployment guide: [`capstone_borehole_analysis/docs/deployment.md`](capstone_borehole_analysis/docs/deployment.md)

## Repository Layout

```text
capstone_borehole_analysis/
  borehole_piecewise_surface.py    Main reconstruction pipeline
  borehole_evaluation.py           Cross-run evaluation report generator
  borehole_metrics.py              Mesh and reconstruction metrics
  outputs*/                        Generated STL/CSV/JSON reconstruction runs
  viewer-react/                    React + Three.js mesh viewer
  tests/                           Python unit tests
  docs/                            Architecture, evaluation, deployment docs
  .github/workflows/               CI and deployment workflows
  Dockerfile                       Containerized test/runtime setup
```

## Tech Stack

- Python
- NumPy, SciPy
- scikit-learn
- scikit-image
- PyVista
- trimesh
- React
- Three.js
- Vite
- Docker
- GitHub Actions
- Vercel

## Running The Project

From the project folder:

```bash
cd capstone_borehole_analysis
python -m unittest discover -s tests
```

To verify the viewer:

```bash
cd capstone_borehole_analysis/viewer-react
npm ci
npm test
npm run build
```

To generate the evaluation report:

```bash
cd capstone_borehole_analysis
python borehole_evaluation.py \
  --run 2800000-dp outputs \
  --run 2750000-single outputs_2750000 \
  --run 2750000-dp outputs_2750000_dp \
  --run 2750000-hybrid-dp outputs_2750000_hybrid_dp \
  --out-dir docs
```

## More Documentation

- [`capstone_borehole_analysis/README.md`](capstone_borehole_analysis/README.md)
- [`capstone_borehole_analysis/docs/pipeline_architecture.md`](capstone_borehole_analysis/docs/pipeline_architecture.md)
- [`capstone_borehole_analysis/docs/model_evaluation.md`](capstone_borehole_analysis/docs/model_evaluation.md)
- [`capstone_borehole_analysis/docs/deployment.md`](capstone_borehole_analysis/docs/deployment.md)

## Project Framing

This project sits at the intersection of applied machine learning, computational geometry, scientific computing, and construction technology. The focus is not just fitting a shape, but building a reproducible reconstruction system with metrics, tests, deployment documentation, and an interface for inspecting the result.
