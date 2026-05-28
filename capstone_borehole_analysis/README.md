# Borehole Reconstruction Pipeline

This folder contains the implementation for the UCSB Data Science capstone borehole reconstruction project.

The pipeline reconstructs a continuous borehole surface from noisy horizontal directional drilling simulation data. It reads VTK/STL inputs, infers the borehole boundary from point-cloud evidence, exports a watertight STL mesh, and produces quality metrics that can be inspected in a browser-based 3D viewer.

## Problem

The simulation data does not directly provide a clean borehole surface. Instead, it gives unstructured 3D particles and tool geometry. The borehole has to be inferred from where soil is missing or displaced.

That is difficult because:

- the point cloud is noisy and irregular
- cavity boundaries can be sparse or incomplete
- individual cross-sections can contain outliers
- fitting each slice independently can create a jagged or spliced mesh

The goal is to turn that raw simulation output into something closer to an engineering artifact: a smooth, continuous, measurable STL surface.

## Pipeline Summary

```text
VTK/STL input
  -> borehole-region point selection
  -> PCA centerline estimation
  -> cross-section slicing
  -> boundary candidate extraction
  -> RANSAC ellipse fitting
  -> dynamic-programming fit selection
  -> smoothing and mesh lofting
  -> STL, CSV, JSON, and viewer outputs
```

## Main Methods

### PCA Centerline Estimation

PCA estimates the dominant direction of the borehole from candidate points. This gives the pipeline a stable axis for slicing the data into local cross-sections.

### Boundary Extraction

The model does not fit against every nearby soil point. It first tries to identify points that are likely to sit near the cavity boundary. The current code supports gradient-based, radial, and hybrid boundary modes.

### RANSAC Ellipse Fitting

Each slice is fit with RANSAC so that outlier points do not dominate the reconstruction. Ellipses are used because the borehole cross-section does not have to be perfectly circular.

### Dynamic-Programming Fit Selection

The pipeline can keep several RANSAC candidates per slice and choose the best global sequence. This helps avoid local mistakes where one slice chooses a fit that looks acceptable alone but creates a bad transition in the final mesh.

### Mesh Lofting

The selected slice fits are smoothed, converted into rings, lofted into a surface, capped, and exported as a watertight STL.

## Important Files

```text
borehole_piecewise_surface.py   Main reconstruction CLI
borehole_evaluation.py          Cross-run evaluation CLI
borehole_metrics.py             Mesh and quality metrics
outputs/                        Primary reconstructed mesh and metrics
viewer-react/                   Interactive 3D mesh viewer
tests/                          Unit tests
docs/                           Architecture, deployment, and evaluation docs
```

## Quick Verification

```bash
python -m unittest discover -s tests
```

Viewer verification:

```bash
cd viewer-react
npm ci
npm test
npm run build
```

## Interactive Viewer

The React/Three.js viewer renders `outputs/borehole_final_smooth.stl` and displays reconstruction metrics from `outputs/borehole_summary.json` and `outputs/borehole_slice_metrics.csv`.

For local development:

```bash
cd viewer-react
npm run dev
```

For a production-equivalent local preview:

```bash
cd viewer-react
npm run build
npm run preview
```

Public users should access a deployed static build, not the Vite development server.

## Documentation

- [Pipeline architecture](docs/pipeline_architecture.md)
- [Model evaluation report](docs/model_evaluation.md)
- [Deployment guide](docs/deployment.md)
