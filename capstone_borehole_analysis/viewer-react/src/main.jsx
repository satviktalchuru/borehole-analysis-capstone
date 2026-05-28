import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Box, Camera, Eye, Palette, RotateCcw } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import summaryUrl from "../../outputs/borehole_summary.json?url";
import sliceMetricsCsv from "../../outputs/borehole_slice_metrics.csv?raw";
import stlUrl from "../../outputs/borehole_final_smooth.stl?url";
import { metricRows, parseSliceMetrics, qualityColorHex } from "./metrics";
import "./styles.css";

function applyQualityColors(geometry, sliceMetrics) {
  if (!sliceMetrics.length) return;
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  const spans = [
    box.max.x - box.min.x,
    box.max.y - box.min.y,
    box.max.z - box.min.z,
  ];
  const axis = spans.indexOf(Math.max(...spans));
  const min = [box.min.x, box.min.y, box.min.z][axis];
  const span = Math.max(spans[axis], 1e-9);
  const positions = geometry.attributes.position;
  const colors = [];
  const color = new THREE.Color();
  for (let i = 0; i < positions.count; i += 1) {
    const coord = positions.getComponent(i, axis);
    const t = Math.max(0, Math.min(1, (coord - min) / span));
    const sliceIndex = Math.min(sliceMetrics.length - 1, Math.max(0, Math.round(t * (sliceMetrics.length - 1))));
    color.set(qualityColorHex(sliceMetrics[sliceIndex]?.cavity_quality ?? 0));
    colors.push(color.r, color.g, color.b);
  }
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
}

function MeshViewport({ wireframe, colorByQuality, resetToken, onMeshStats, onStatus }) {
  const hostRef = useRef(null);
  const controlsRef = useRef(null);
  const cameraRef = useRef(null);
  const meshRef = useRef(null);
  const initialViewRef = useRef(null);
  const sliceMetrics = useMemo(() => parseSliceMetrics(sliceMetricsCsv), []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f7f8);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(host.clientWidth, host.clientHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);

    const camera = new THREE.PerspectiveCamera(42, host.clientWidth / host.clientHeight, 0.01, 5000);
    camera.position.set(2.5, 1.8, 2.2);
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controlsRef.current = controls;

    const hemi = new THREE.HemisphereLight(0xffffff, 0x7b8794, 2.1);
    scene.add(hemi);
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.8);
    keyLight.position.set(4, 5, 6);
    scene.add(keyLight);

    const grid = new THREE.GridHelper(4, 16, 0xa8b4bd, 0xd4dbdf);
    grid.position.y = -0.75;
    scene.add(grid);
    const axes = new THREE.AxesHelper(0.65);
    axes.position.set(-1.55, -0.72, -1.55);
    scene.add(axes);

    const loader = new STLLoader();
    onStatus("loading");
    loader.load(
      stlUrl,
      (geometry) => {
        geometry.computeVertexNormals();
        applyQualityColors(geometry, sliceMetrics);
        geometry.center();

        const material = new THREE.MeshStandardMaterial({
          color: 0x1f7a8c,
          vertexColors: colorByQuality,
          metalness: 0.12,
          roughness: 0.42,
          side: THREE.DoubleSide,
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.rotation.x = -Math.PI / 2;
        scene.add(mesh);
        meshRef.current = mesh;

        const box = new THREE.Box3().setFromObject(mesh);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const distance = maxDim / (2 * Math.tan((camera.fov * Math.PI) / 360));

        controls.target.copy(center);
        camera.position.copy(center).add(new THREE.Vector3(distance * 0.9, distance * 0.65, distance * 1.25));
        camera.near = Math.max(distance / 100, 0.001);
        camera.far = distance * 100;
        camera.updateProjectionMatrix();
        controls.update();

        initialViewRef.current = {
          position: camera.position.clone(),
          target: controls.target.clone(),
        };
        onMeshStats({
          vertices: geometry.attributes.position.count,
          triangles: geometry.index ? geometry.index.count / 3 : geometry.attributes.position.count / 3,
          width: size.x,
          height: size.y,
          depth: size.z,
        });
        onStatus("ready");
      },
      undefined,
      () => onStatus("error"),
    );

    const resize = () => {
      if (!host.clientWidth || !host.clientHeight) return;
      camera.aspect = host.clientWidth / host.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(host.clientWidth, host.clientHeight);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);

    let frame = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(animate);
    };
    animate();

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      geometryCleanup(scene);
    };
  }, [colorByQuality, onMeshStats, onStatus, sliceMetrics]);

  useEffect(() => {
    if (meshRef.current) {
      meshRef.current.material.wireframe = wireframe;
    }
  }, [wireframe]);

  useEffect(() => {
    if (meshRef.current) {
      meshRef.current.material.vertexColors = colorByQuality;
      meshRef.current.material.needsUpdate = true;
    }
  }, [colorByQuality]);

  useEffect(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const view = initialViewRef.current;
    if (!camera || !controls || !view || resetToken === 0) return;
    camera.position.copy(view.position);
    controls.target.copy(view.target);
    controls.update();
  }, [resetToken]);

  return <div className="viewport" ref={hostRef} aria-label="Interactive borehole STL viewer" />;
}

function geometryCleanup(scene) {
  scene.traverse((object) => {
    if (object.geometry) object.geometry.dispose();
    if (object.material) {
      if (Array.isArray(object.material)) {
        object.material.forEach((material) => material.dispose());
      } else {
        object.material.dispose();
      }
    }
  });
}

function App() {
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState("");
  const [meshStats, setMeshStats] = useState(null);
  const [wireframe, setWireframe] = useState(false);
  const [colorByQuality, setColorByQuality] = useState(true);
  const [resetToken, setResetToken] = useState(0);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    fetch(summaryUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(setSummary)
      .catch(() => setSummaryError("Summary metrics unavailable"));
  }, []);

  const rows = useMemo(() => metricRows(summary), [summary]);

  return (
    <main className="app-shell">
      <section className="viewer-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">3D Borehole Reconstruction</p>
            <h1>Mesh Viewer</h1>
          </div>
          <div className="toolbar" aria-label="Viewer controls">
            <button type="button" onClick={() => setColorByQuality((value) => !value)} title="Toggle quality colors">
              <Palette size={18} />
              <span>{colorByQuality ? "Solid color" : "Quality color"}</span>
            </button>
            <button type="button" onClick={() => setWireframe((value) => !value)} title="Toggle wireframe">
              <Eye size={18} />
              <span>{wireframe ? "Solid" : "Wireframe"}</span>
            </button>
            <button type="button" onClick={() => setResetToken((value) => value + 1)} title="Reset camera">
              <RotateCcw size={18} />
              <span>Reset</span>
            </button>
          </div>
        </header>
        <div className="canvas-wrap">
          <MeshViewport
            wireframe={wireframe}
            colorByQuality={colorByQuality}
            resetToken={resetToken}
            onMeshStats={setMeshStats}
            onStatus={setStatus}
          />
          {status !== "ready" && (
            <div className="status-overlay">
              <Box size={28} />
              <span>{status === "error" ? "Unable to load STL mesh" : "Loading STL mesh"}</span>
            </div>
          )}
        </div>
      </section>

      <aside className="inspector">
        <div className="inspector-section">
          <div className="section-title">
            <Activity size={18} />
            <h2>Quality Metrics</h2>
          </div>
          <div className="quality-legend" aria-label="Mesh quality color legend">
            <span>Low</span>
            <div className="legend-ramp" />
            <span>High</span>
          </div>
          {summaryError ? (
            <p className="muted">{summaryError}</p>
          ) : (
            <dl className="metric-list">
              {rows.map((row) => (
                <div className="metric-row" key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>

        <div className="inspector-section">
          <div className="section-title">
            <Camera size={18} />
            <h2>Mesh Stats</h2>
          </div>
          <dl className="metric-list">
            <div className="metric-row">
              <dt>Vertices</dt>
              <dd>{meshStats ? meshStats.vertices.toLocaleString() : "Loading"}</dd>
            </div>
            <div className="metric-row">
              <dt>Triangles</dt>
              <dd>{meshStats ? Math.round(meshStats.triangles).toLocaleString() : "Loading"}</dd>
            </div>
            <div className="metric-row">
              <dt>Bounds</dt>
              <dd>
                {meshStats
                  ? `${meshStats.width.toFixed(2)} x ${meshStats.height.toFixed(2)} x ${meshStats.depth.toFixed(2)}`
                  : "Loading"}
              </dd>
            </div>
          </dl>
        </div>
      </aside>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
