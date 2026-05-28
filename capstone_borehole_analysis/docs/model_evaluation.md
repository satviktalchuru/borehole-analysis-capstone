# Borehole Reconstruction Evaluation

| Dataset | Accepted Slices | Watertight | Components | Cavity Quality | Max Radius Jump | Roughness CV |
|---|---:|:---:|---:|---:|---:|---:|
| 2800000-dp | 132/132 | yes | 1 | 0.1260 | 0.002766 | 0.0138 |
| 2750000-single | 137/137 | yes | 1 | 0.1389 | 0.001855 | 0.0131 |
| 2750000-dp | 137/137 | yes | 1 | 0.1579 | 0.001862 | 0.0132 |
| 2750000-hybrid-dp | 137/137 | yes | 1 | 0.1463 | 0.002082 | 0.0154 |

Lower `max_radius_jump` and `radius_roughness_cv` indicate smoother radius continuity. 
Higher `mean_cavity_quality` indicates better agreement between the fitted cavity boundary and local point-cloud evidence.
