const METRIC_DEFINITIONS = [
  ["accepted_slices", "Accepted slices"],
  ["slice_success_rate", "Slice success"],
  ["mean_inlier_ratio", "Mean inlier ratio"],
  ["mean_cavity_quality", "Cavity quality"],
  ["radius_roughness_cv", "Radius roughness"],
];

const PERCENT_KEYS = new Set([
  "slice_success_rate",
  "slice_analysis_rate",
  "fit_success_of_analyzed_rate",
  "mean_inlier_ratio",
  "mean_perimeter_completeness",
  "mean_soil_inside_point_frac",
  "mean_balanced_accuracy",
  "mean_cavity_quality",
  "radius_roughness_cv",
]);

export function formatMetric(key, value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return String(value ?? "Unavailable");
  }
  if (PERCENT_KEYS.has(key)) {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (Number.isInteger(value)) {
    return value.toLocaleString();
  }
  if (Math.abs(value) < 0.001 && value !== 0) {
    return value.toPrecision(3);
  }
  return Number(value.toFixed(4)).toString();
}

export function metricRows(summary) {
  if (!summary) {
    return [];
  }
  return METRIC_DEFINITIONS.filter(([key]) => key in summary).map(([key, label]) => ({
    label,
    value: formatMetric(key, summary[key]),
  }));
}

export function parseSliceMetrics(csvText) {
  const lines = csvText.trim().split(/\r?\n/);
  if (lines.length < 2) {
    return [];
  }
  const headers = lines[0].split(",").map((header) => header.trim());
  return lines.slice(1).filter(Boolean).map((line) => {
    const values = line.split(",");
    return Object.fromEntries(
      headers.map((header, index) => {
        const raw = values[index]?.trim() ?? "";
        const numeric = Number(raw);
        return [header, Number.isFinite(numeric) && raw !== "" ? numeric : raw];
      }),
    );
  });
}

function interpolateChannel(start, end, t) {
  return Math.round(start + (end - start) * t);
}

function rgbToHex([r, g, b]) {
  return `#${[r, g, b].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

export function qualityColorHex(value) {
  const t = Math.max(0, Math.min(1, Number(value) || 0));
  const red = [0xd9, 0x4b, 0x3d];
  const yellow = [0xf2, 0xc1, 0x4e];
  const green = [0x2f, 0x9e, 0x6d];
  if (t <= 0.5) {
    return rgbToHex(red.map((channel, index) => interpolateChannel(channel, yellow[index], t / 0.5)));
  }
  return rgbToHex(yellow.map((channel, index) => interpolateChannel(channel, green[index], (t - 0.5) / 0.5)));
}
