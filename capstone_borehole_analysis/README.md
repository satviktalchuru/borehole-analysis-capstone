# Borehole Reconstruction

Production-style reconstruction pipeline for converting noisy 3D HDD simulation particle data into a watertight borehole STL mesh, quality metrics, and an interactive Three.js viewer.

## What This Project Does

- Reconstructs borehole geometry from VTK point-cloud simulation data.
- Uses PCA centerline estimation, RANSAC ellipse fitting, gradient/radial boundary extraction, dynamic-programming candidate selection, smoothing, and mesh lofting.
- Exports CAD-ready STL surfaces plus JSON/CSV quality reports.
- Provides a production-built web viewer for inspecting the reconstructed mesh and fit quality.

## Repository Layout

```text
borehole_piecewise_surface.py   Reconstruction pipeline CLI
borehole_evaluation.py          Cross-run model evaluation CLI
borehole_metrics.py             Mesh and reconstruction metrics
outputs*/                       Generated STL/CSV/JSON reconstruction runs
viewer-react/                   React + Three.js mesh viewer
tests/                          Python unit tests
docs/                           Evaluation, architecture, and deployment docs
.github/workflows/              CI and deployment automation
vercel.json                     Static production deployment config
```

## Quick Verification

```bash
python -m unittest discover -s tests
cd viewer-react
npm ci
npm test
npm run build
```

## Production Viewer

For development, use:

```bash
cd viewer-react
npm run dev
```

For a production-equivalent local preview, use:

```bash
cd viewer-react
npm run build
npm run preview
```

The deployed site should always serve `viewer-react/dist`, not the Vite dev server.

## Documentation

- [Pipeline architecture](docs/pipeline_architecture.md)
- [Deployment guide](docs/deployment.md)
- [Model evaluation report](docs/model_evaluation.md)
