# Deployment Guide

This project should be deployed as a static production build of the React viewer. Do not expose `npm run dev`; that command starts Vite's development server and is only for local iteration.

## Recommended Deployment: Vercel

The repository includes a root-level `vercel.json` so Vercel can build the viewer while still having access to the generated reconstruction files in `outputs/`.

Vercel settings:

- Framework preset: Vite
- Install command: `cd viewer-react && npm ci`
- Build command: `cd viewer-react && npm ci && npm run build`
- Output directory: `viewer-react/dist`

The committed `vercel.json` already encodes these settings.

## One-Time Setup

1. Push this repository to GitHub.
2. Import the GitHub repository into Vercel.
3. Keep the project root as the repository root, not `viewer-react/`.
4. Deploy.

Vercel will run the production build and serve the static files from `viewer-react/dist`.

## GitHub Actions Deployment

`.github/workflows/deploy-viewer.yml` deploys the viewer on pushes to `main` and can also be run manually from GitHub Actions.

Add these GitHub repository secrets:

```text
VERCEL_TOKEN
VERCEL_ORG_ID
VERCEL_PROJECT_ID
```

Get `VERCEL_TOKEN` from Vercel account settings. `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` are written into `.vercel/project.json` after running:

```bash
vercel link
```

Do not commit `.vercel/project.json` if it contains personal/team-specific project IDs unless you intentionally want the repo tied to that Vercel project.

## Local Production Check

Before deploying:

```bash
python -m unittest discover -s tests
cd viewer-react
npm ci
npm test
npm run build
npm run preview
```

`npm run preview` serves the already-built `dist/` folder. It is acceptable for local production verification, but it is still not what public users should access. Public users should access the Vercel deployment URL.

## What Gets Deployed

The deployed viewer includes:

- `outputs/borehole_final_smooth.stl`
- `outputs/borehole_summary.json`
- `outputs/borehole_slice_metrics.csv`
- React UI bundle
- Three.js mesh viewer
- quality-color visualization

If you want to deploy a different reconstruction run, copy that run's STL/JSON/CSV into `outputs/` before building.
