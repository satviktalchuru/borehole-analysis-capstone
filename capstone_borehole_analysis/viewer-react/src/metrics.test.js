import { describe, expect, it } from "vitest";

import { formatMetric, metricRows, parseSliceMetrics, qualityColorHex } from "./metrics";

describe("formatMetric", () => {
  it("formats rates as percentages and scalar values compactly", () => {
    expect(formatMetric("slice_success_rate", 0.875)).toBe("87.5%");
    expect(formatMetric("accepted_slices", 132)).toBe("132");
    expect(formatMetric("mean_curvature", 0.000229)).toBe("0.000229");
  });
});

describe("metricRows", () => {
  it("keeps the dashboard focused on reconstruction quality metrics", () => {
    const rows = metricRows({
      accepted_slices: 132,
      slice_success_rate: 1,
      mean_inlier_ratio: 0.6351,
      mean_cavity_quality: 0.1223,
      radius_roughness_cv: 0.06042,
      stl: "outputs/borehole_final_smooth.stl",
    });

    expect(rows).toEqual([
      { label: "Accepted slices", value: "132" },
      { label: "Slice success", value: "100.0%" },
      { label: "Mean inlier ratio", value: "63.5%" },
      { label: "Cavity quality", value: "12.2%" },
      { label: "Radius roughness", value: "6.0%" },
    ]);
  });
});

describe("parseSliceMetrics", () => {
  it("parses numeric CSV slice quality rows", () => {
    const rows = parseSliceMetrics("slice_index,cavity_quality,regularized_equivalent_radius\n0,0.25,0.04\n1,0.75,0.05\n");

    expect(rows).toEqual([
      { slice_index: 0, cavity_quality: 0.25, regularized_equivalent_radius: 0.04 },
      { slice_index: 1, cavity_quality: 0.75, regularized_equivalent_radius: 0.05 },
    ]);
  });
});

describe("qualityColorHex", () => {
  it("maps low, medium, and high quality to red-yellow-green colors", () => {
    expect(qualityColorHex(0)).toBe("#d94b3d");
    expect(qualityColorHex(0.5)).toBe("#f2c14e");
    expect(qualityColorHex(1)).toBe("#2f9e6d");
  });
});
