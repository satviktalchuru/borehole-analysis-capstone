# Borehole Analysis Capstone

UCSB Data Science capstone project for reconstructing horizontal directional drilling borehole geometry from noisy 3D simulation data.

The main project lives in [`capstone_borehole_analysis/`](capstone_borehole_analysis/).

## Highlights

- Python reconstruction pipeline for VTK/STL simulation data.
- PCA centerline estimation, RANSAC ellipse fitting, boundary extraction, dynamic-programming fit selection, smoothing, and watertight STL export.
- React/Three.js viewer for inspecting the reconstructed 3D mesh and quality metrics.
- Unit tests, Docker support, GitHub Actions CI, and Vercel deployment configuration.

## Start Here

Read the project documentation:

- [`capstone_borehole_analysis/README.md`](capstone_borehole_analysis/README.md)
- [`capstone_borehole_analysis/docs/pipeline_architecture.md`](capstone_borehole_analysis/docs/pipeline_architecture.md)
- [`capstone_borehole_analysis/docs/deployment.md`](capstone_borehole_analysis/docs/deployment.md)
