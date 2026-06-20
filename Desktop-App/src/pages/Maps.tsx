import { useEffect, useRef, useState, MutableRefObject } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-draw";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { readTextFile } from "@tauri-apps/plugin-fs";
import {
  Download, FolderOpen, Layers, Info, CheckCircle2, Loader2, X, FolderInput,
} from "lucide-react";
import { cmd } from "../lib/tauri";
import { useAppStore } from "../lib/store";
import { generateId, cn } from "../lib/utils";
import type { BBox, DownloadProgress, Region, TileEstimate, TileSource } from "../lib/types";

const ESRI_SATELLITE =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const ESRI_LABELS =
  "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";

function bboxAreaKm2(bbox: BBox): number {
  const latCenter = ((bbox.lat_min + bbox.lat_max) / 2) * (Math.PI / 180);
  const ns = (bbox.lat_max - bbox.lat_min) * 111.32;
  const ew = (bbox.lon_max - bbox.lon_min) * 111.32 * Math.cos(latCenter);
  return Math.abs(ns * ew);
}

type DrawMode = "rectangle" | "triangle" | "polygon";

const SOURCES: Record<TileSource, { label: string; maxZoom: number; free: boolean; description: string }> = {
  esri:   { label: "ESRI World Imagery", maxZoom: 19, free: true,  description: "No API key required. Global coverage." },
  mapbox: { label: "Mapbox Satellite",   maxZoom: 22, free: false, description: "Up to zoom 22. Sharpest imagery." },
  bing:   { label: "Bing Maps Aerial",   maxZoom: 20, free: false, description: "Up to zoom 20. Requires Bing API key." },
};

const DRAW_MODES: { mode: DrawMode; label: string; hint: string }[] = [
  { mode: "rectangle", label: "Rectangle", hint: "Click and drag to select a rectangular region" },
  { mode: "triangle",  label: "Triangle",  hint: "Click 3 corner points — shape closes automatically" },
  { mode: "polygon",   label: "Polygon",   hint: "Click to add points. Click the first point to close" },
];

// ── Bing Maps custom tile layer (quadkey addressing) ──────────────────────────
function BingTileLayer({ apiKey }: { apiKey: string }) {
  const map = useMap();
  useEffect(() => {
    const BingLayer = (L.TileLayer as any).extend({
      getTileUrl(c: any) {
        let qk = "";
        for (let i = c.z; i > 0; i--) {
          let d = 0;
          const m = 1 << (i - 1);
          if (c.x & m) d += 1;
          if (c.y & m) d += 2;
          qk += d;
        }
        const s = (Math.abs(c.x) + Math.abs(c.y)) % 4;
        return `https://t${s}.ssl.ak.tiles.virtualearth.net/tiles/a${qk}.jpeg?g=7&token=${apiKey}`;
      },
    });
    const layer = new BingLayer("", { maxZoom: 20, attribution: "© Microsoft / Bing Maps" });
    layer.addTo(map);
    return () => { map.removeLayer(layer); };
  }, [map, apiKey]);
  return null;
}

// ── Draw handler — direct Leaflet API, no leaflet-draw toolbar ───────────────
// Rectangle: manual mousedown/mousemove/mouseup (L.Draw.Rectangle is unreliable
//            in WebView2 due to pointer-capture behaviour on Windows).
// Triangle/Polygon: L.Draw.Polygon with click-to-place vertices.
// drawKey increments each time a mode button is clicked, forcing a fresh session.
function DrawControlInner({
  onBBoxChange,
  featureGroupRef,
  mode,
  drawKey,
}: {
  onBBoxChange: (b: BBox | null) => void;
  featureGroupRef: MutableRefObject<L.FeatureGroup | null>;
  mode: DrawMode;
  drawKey: number;
}) {
  const map = useMap();
  const handlerRef = useRef<{ disable: () => void } | null>(null);

  useEffect(() => {
    if (!featureGroupRef.current) {
      featureGroupRef.current = L.featureGroup().addTo(map);
    }
    const fg = featureGroupRef.current;
    const shapeStyle = { color: "#06B6D4", weight: 2, fillOpacity: 0.12 };

    handlerRef.current?.disable();

    if (mode === "rectangle") {
      const container = map.getContainer();
      container.style.cursor = "crosshair";

      let startLatLng: L.LatLng | null = null;
      let previewRect: L.Rectangle | null = null;

      const onMouseDown = (e: L.LeafletMouseEvent) => {
        startLatLng = e.latlng;
        map.dragging.disable();
        fg.clearLayers();
        onBBoxChange(null);
      };

      const onMouseMove = (e: L.LeafletMouseEvent) => {
        if (!startLatLng) return;
        if (previewRect) fg.removeLayer(previewRect);
        previewRect = L.rectangle([startLatLng, e.latlng], shapeStyle);
        fg.addLayer(previewRect);
      };

      const onMouseUp = (e: L.LeafletMouseEvent) => {
        if (!startLatLng) return;
        map.dragging.enable();
        const bounds = L.latLngBounds(startLatLng, e.latlng);
        if (bounds.getNorth() !== bounds.getSouth()) {
          onBBoxChange({
            lat_min: bounds.getSouth(),
            lat_max: bounds.getNorth(),
            lon_min: bounds.getWest(),
            lon_max: bounds.getEast(),
          });
        }
        startLatLng = null;
        previewRect = null;
      };

      map.on("mousedown", onMouseDown);
      map.on("mousemove", onMouseMove);
      map.on("mouseup", onMouseUp);

      handlerRef.current = {
        disable: () => {
          map.off("mousedown", onMouseDown);
          map.off("mousemove", onMouseMove);
          map.off("mouseup", onMouseUp);
          map.dragging.enable();
          container.style.cursor = "";
        },
      };
    } else {
      const handler = new (L.Draw as any).Polygon(map, {
        shapeOptions: shapeStyle,
        allowIntersection: false,
        showArea: false,
      });
      handler.enable();

      let vertexCount = 0;
      const onDrawStart = () => { vertexCount = 0; };
      const onDrawVertex = () => {
        if (mode !== "triangle") return;
        vertexCount += 1;
        if (vertexCount >= 3) {
          vertexCount = 0;
          setTimeout(() => handler._finishShape?.(), 50);
        }
      };
      const onCreate = (e: any) => {
        fg.clearLayers();
        fg.addLayer(e.layer);
        const bounds: L.LatLngBounds = e.layer.getBounds();
        onBBoxChange({
          lat_min: bounds.getSouth(),
          lat_max: bounds.getNorth(),
          lon_min: bounds.getWest(),
          lon_max: bounds.getEast(),
        });
      };

      map.on(L.Draw.Event.DRAWSTART,  onDrawStart);
      map.on(L.Draw.Event.DRAWVERTEX, onDrawVertex);
      map.on(L.Draw.Event.CREATED,    onCreate);

      handlerRef.current = {
        disable: () => {
          handler.disable();
          map.off(L.Draw.Event.DRAWSTART,  onDrawStart);
          map.off(L.Draw.Event.DRAWVERTEX, onDrawVertex);
          map.off(L.Draw.Event.CREATED,    onCreate);
        },
      };
    }

    return () => { handlerRef.current?.disable(); };
  }, [map, mode, drawKey, onBBoxChange, featureGroupRef]);

  return null;
}

// ── Main Maps page ────────────────────────────────────────────────────────────
export function Maps() {
  const { profile, regions, addRegion } = useAppStore();
  const featureGroupRef = useRef<L.FeatureGroup | null>(null);

  const [source,     setSource]     = useState<TileSource>("esri");
  const [drawMode,   setDrawMode]   = useState<DrawMode>("rectangle");
  const [drawKey,    setDrawKey]    = useState(0);
  const [bbox,       setBbox]       = useState<BBox | null>(null);
  const [zoom,       setZoom]       = useState(17);
  const [regionName, setRegionName] = useState("Flight Region");
  const [outputDir,  setOutputDir]  = useState("");
  const [estimate,   setEstimate]   = useState<TileEstimate | null>(null);
  const [downloading,setDownloading]= useState(false);
  const [progress,   setProgress]   = useState<DownloadProgress | null>(null);
  const [done,       setDone]       = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const sourceConfig = SOURCES[source];
  const apiKey   = source === "mapbox" ? (profile?.mapbox_key ?? "") : (profile?.bing_key ?? "");
  const missingKey = !sourceConfig.free && !apiKey;
  const currentMode = DRAW_MODES.find((d) => d.mode === drawMode)!;

  useEffect(() => {
    if (!bbox) { setEstimate(null); return; }
    cmd.estimateTiles(bbox, zoom).then(setEstimate).catch(console.error);
  }, [bbox, zoom]);

  const handleSourceChange = (s: TileSource) => {
    setSource(s);
    if (zoom > SOURCES[s].maxZoom) setZoom(SOURCES[s].maxZoom);
  };

  // Clicking a mode button always triggers a fresh draw session (drawKey++) and
  // clears the existing selection, even if the mode hasn't changed.
  const handleModeChange = (m: DrawMode) => {
    setDrawMode(m);
    setDrawKey((k) => k + 1);
    setBbox(null);
    setDone(false);
    setError(null);
    featureGroupRef.current?.clearLayers();
  };

  const clearSelection = () => {
    setBbox(null);
    setEstimate(null);
    setDone(false);
    setError(null);
    featureGroupRef.current?.clearLayers();
    // Re-enable drawing after clearing
    setDrawKey((k) => k + 1);
  };

  const handlePickDir = async () => {
    const dir = await open({ directory: true, multiple: false, title: "Select output folder" });
    if (dir) setOutputDir(dir as string);
  };

  const importFromFolder = async () => {
    const dir = await open({ directory: true, multiple: false, title: "Select region folder (must contain metadata.json)" });
    if (!dir) return;
    const folder = dir as string;
    try {
      const text = await readTextFile(`${folder}/metadata.json`);
      const meta = JSON.parse(text);
      if (meta.origin_lat == null || meta.origin_lon == null || !meta.gsd_m_per_px || !meta.width_px || !meta.height_px) {
        throw new Error("metadata.json is missing required fields (origin_lat, origin_lon, gsd_m_per_px, width_px, height_px)");
      }
      const { origin_lat, origin_lon, gsd_m_per_px, width_px, height_px, zoom: z = 17, source: src = "esri" } = meta;
      const cosLat = Math.cos(origin_lat * Math.PI / 180);
      const gsdEw = 40075016.686 * cosLat / (256 * Math.pow(2, z));
      const deltaLon = width_px * gsdEw / (111320 * cosLat);
      const deltaLat = height_px * gsdEw / 111320;
      const bbox: BBox = {
        lat_min: origin_lat - deltaLat,
        lat_max: origin_lat,
        lon_min: origin_lon,
        lon_max: origin_lon + deltaLon,
      };
      const centerLat = (bbox.lat_min + bbox.lat_max) / 2;
      const centerLon = (bbox.lon_min + bbox.lon_max) / 2;
      const locationLabel = await reverseGeocode(centerLat, centerLon);
      const folderName = folder.split(/[/\\]/).pop() ?? "Imported Region";
      const region: Region = {
        id: generateId(),
        name: folderName,
        ...bbox,
        zoom: z,
        source: src,
        output_path: folder,
        last_downloaded: new Date().toISOString(),
        gsd_m_per_px,
        location_label: locationLabel,
      };
      addRegion(region);
      await cmd.saveRegions([...regions, region]);
      setDone(true);
      setError(null);
    } catch (e) {
      setError(`Import failed: ${e}`);
    }
  };

  const reverseGeocode = async (lat: number, lon: number): Promise<string | undefined> => {
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=10`,
        { headers: { "Accept-Language": "en", "User-Agent": "Macula VPS Desktop/0.1" } }
      );
      const j = await res.json();
      const a = j.address ?? {};
      const city = a.city ?? a.town ?? a.village ?? a.county ?? a.state_district ?? a.state ?? "";
      const country = a.country ?? "";
      return city && country ? `${city}, ${country}` : country || city || undefined;
    } catch {
      return undefined;
    }
  };

  const handleDownload = async () => {
    if (!bbox || !outputDir || missingKey) return;
    setDownloading(true);
    setDone(false);
    setError(null);
    setProgress(null);
    const unlisten = await listen<DownloadProgress>("tile-progress", (e) => setProgress(e.payload));
    try {
      await cmd.downloadTiles(bbox, zoom, outputDir, source, apiKey || undefined);
      const centerLat = (bbox.lat_min + bbox.lat_max) / 2;
      const centerLon = (bbox.lon_min + bbox.lon_max) / 2;
      const locationLabel = await reverseGeocode(centerLat, centerLon);
      const region: Region = {
        id: generateId(),
        name: regionName || "Unnamed Region",
        ...bbox,
        zoom,
        source,
        output_path: outputDir,
        last_downloaded: new Date().toISOString(),
        tile_count: estimate?.tile_count,
        gsd_m_per_px: estimate?.gsd_m_per_px,
        file_size_mb: estimate?.estimated_mb,
        location_label: locationLabel,
      };
      addRegion(region);
      const next = [...regions, region];
      await cmd.saveRegions(next);
      setDone(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setDownloading(false);
      unlisten();
    }
  };

  return (
    <div className="flex h-full animate-fade-in">
      {/* Map */}
      <div className="flex-1 relative">
        <MapContainer center={[37.775, -122.418]} zoom={14} minZoom={3} className="w-full h-full" zoomControl>
          {(source === "esri" || missingKey) && (
            <TileLayer url={ESRI_SATELLITE} attribution="© Esri" maxZoom={20} maxNativeZoom={19} />
          )}
          {source === "mapbox" && !missingKey && (
            <TileLayer
              url={`https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}.jpg90?access_token=${apiKey}`}
              attribution="© Mapbox © OpenStreetMap"
              maxZoom={22}
            />
          )}
          {source === "bing" && !missingKey && <BingTileLayer apiKey={apiKey} />}
          {/* Labels / roads / city names overlay — free, no key, always shown */}
          <TileLayer url={ESRI_LABELS} attribution="" maxZoom={20} opacity={0.85} />

          <DrawControlInner
            onBBoxChange={setBbox}
            featureGroupRef={featureGroupRef}
            mode={drawMode}
            drawKey={drawKey}
          />
        </MapContainer>

        {/* Floating hint */}
        {!bbox && (
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-bg-surface/90 border border-border rounded-full px-4 py-2 text-xs text-slate-400 backdrop-blur-sm pointer-events-none">
            {currentMode.hint}
          </div>
        )}
      </div>

      {/* Side panel */}
      <div className="w-80 bg-bg-surface border-l border-border flex flex-col overflow-y-auto">
        <div className="px-5 py-4 border-b border-border">
          <h2 className="section-title">Region Download</h2>
          <p className="text-slate-400 text-xs mt-1">
            Define a flight area, then download the satellite mosaic.
          </p>
        </div>

        <div className="p-5 space-y-5 flex-1">
          {/* Region name */}
          <div>
            <label className="label">Region name</label>
            <input
              className="input-field"
              value={regionName}
              onChange={(e) => setRegionName(e.target.value)}
              placeholder="Flight Region"
            />
          </div>

          {/* Imagery source */}
          <div>
            <label className="label">Imagery source</label>
            <div className="space-y-1 mt-1">
              {(Object.entries(SOURCES) as [TileSource, (typeof SOURCES)[TileSource]][]).map(
                ([key, cfg]) => (
                  <button
                    key={key}
                    onClick={() => handleSourceChange(key)}
                    className={cn(
                      "w-full flex items-center justify-between px-3 py-2.5 rounded-lg border text-xs transition-colors text-left",
                      source === key
                        ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-300"
                        : "bg-bg-card border-border text-slate-400 hover:border-slate-600 hover:text-slate-300"
                    )}
                  >
                    <div>
                      <div className="font-medium">{cfg.label}</div>
                      <div className="text-[10px] mt-0.5 opacity-70">{cfg.description}</div>
                    </div>
                    <span
                      className={cn(
                        "ml-2 shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium",
                        cfg.free
                          ? "bg-emerald-500/15 text-emerald-400"
                          : "bg-amber-500/15 text-amber-400"
                      )}
                    >
                      {cfg.free ? "Free" : `Z${cfg.maxZoom}`}
                    </span>
                  </button>
                )
              )}
            </div>
            {missingKey && (
              <div className="mt-2 text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2.5 py-2">
                ⚠ No API key — add yours in Settings → Imagery Sources. Preview using ESRI.
              </div>
            )}
          </div>

          {/* Selection tool */}
          <div>
            <label className="label">Selection tool</label>
            <div className="grid grid-cols-3 gap-1 mt-1">
              {DRAW_MODES.map(({ mode, label }) => (
                <button
                  key={mode}
                  onClick={() => handleModeChange(mode)}
                  className={cn(
                    "py-2 rounded-lg border text-xs font-medium transition-colors",
                    drawMode === mode
                      ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-300"
                      : "bg-bg-card border-border text-slate-400 hover:text-slate-300 hover:border-slate-600"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-slate-600 mt-1.5">
              {drawMode === "triangle"
                ? "Closes automatically after 3 points."
                : drawMode === "polygon"
                ? "Click the first point to close. Crossing lines are blocked."
                : "Tiles are downloaded for the drawn bounding area."}
            </p>
          </div>

          {/* Zoom level */}
          <div>
            <label className="label flex items-center justify-between">
              <span>Zoom level</span>
              <span className="text-cyan-400 font-mono">{zoom}</span>
            </label>
            <input
              type="range"
              min={15}
              max={sourceConfig.maxZoom}
              step={1}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
              className="w-full mt-2"
            />
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>15 (1.2 m/px)</span>
              <span>Z{sourceConfig.maxZoom}</span>
            </div>
          </div>

          {/* BBox / selection info */}
          {bbox ? (
            <div className="bg-bg-card border border-border rounded-lg p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-300">Selected Region</span>
                <button onClick={clearSelection} className="text-slate-500 hover:text-slate-300">
                  <X size={13} />
                </button>
              </div>
              <div className="text-[11px] font-mono text-slate-400 space-y-0.5">
                <div>Lat {bbox.lat_min.toFixed(5)} → {bbox.lat_max.toFixed(5)}</div>
                <div>Lon {bbox.lon_min.toFixed(5)} → {bbox.lon_max.toFixed(5)}</div>
              </div>
              <div className="bg-bg-elevated rounded px-2 py-1.5 text-center">
                <span className="text-lg font-bold text-cyan-400 font-mono">
                  {bboxAreaKm2(bbox).toFixed(2)}
                </span>
                <span className="text-xs text-slate-400 ml-1">km²</span>
              </div>
              {estimate && (
                <div className="border-t border-border pt-2 space-y-1">
                  {estimate.too_large && (
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-2.5 py-2 text-red-400 text-[10px]">
                      ⚠ Region too large ({estimate.tile_count.toLocaleString()}+ tiles). Draw a smaller area — keep it under ~18 km × 18 km.
                    </div>
                  )}
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-400">Tiles</span>
                    <span className={cn("font-medium", estimate.too_large ? "text-red-400" : "text-slate-200")}>
                      {estimate.tile_count.toLocaleString()} ({estimate.nx}×{estimate.ny})
                    </span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-400">Est. size</span>
                    <span className="text-slate-200 font-medium">{estimate.estimated_mb.toFixed(1)} MB</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-400">GSD</span>
                    <span className="text-slate-200 font-medium">{estimate.gsd_m_per_px.toFixed(3)} m/px</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-bg-card border border-dashed border-border rounded-lg p-4 text-center">
              <Layers size={20} className="text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-500">{currentMode.hint}</p>
            </div>
          )}

          {/* Output folder */}
          <div>
            <label className="label">Output folder</label>
            <div className="flex gap-2">
              <input
                className="input-field flex-1 text-xs font-mono"
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
                placeholder="Choose folder…"
                readOnly
              />
              <button onClick={handlePickDir} className="btn-secondary px-3">
                <FolderOpen size={15} />
              </button>
            </div>
          </div>

          {/* Progress */}
          {downloading && progress && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Downloading tiles…</span>
                <span>{progress.current} / {progress.total}</span>
              </div>
              <div className="h-2 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  className="h-full bg-cyan-500 rounded-full transition-all duration-200"
                  style={{ width: `${progress.percent}%` }}
                />
              </div>
            </div>
          )}

          {done && (
            <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2 text-emerald-400 text-sm">
              <CheckCircle2 size={15} />
              Mosaic saved — region added to library.
            </div>
          )}
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-red-400 text-xs">
              {error}
            </div>
          )}

          <div className="text-[10px] text-slate-500 flex items-start gap-1.5 bg-bg-card rounded-lg p-2.5 border border-border">
            <Info size={11} className="mt-0.5 shrink-0 text-cyan-500" />
            {source === "esri"
              ? "ESRI World Imagery — free, no key required. Tiles cached locally."
              : source === "mapbox"
              ? "Mapbox Satellite — zoom up to 22. Add your access token in Settings."
              : "Bing Maps Aerial — zoom up to 20. Add your API key in Settings."}
          </div>
        </div>

        <div className="p-5 border-t border-border space-y-2">
          <button
            onClick={handleDownload}
            disabled={!bbox || !outputDir || downloading || missingKey || !!estimate?.too_large}
            className="btn-primary w-full justify-center"
          >
            {downloading ? (
              <><Loader2 size={15} className="animate-spin" /> Downloading…</>
            ) : (
              <><Download size={15} /> Download Mosaic</>
            )}
          </button>
          <button
            onClick={importFromFolder}
            className="btn-secondary w-full justify-center text-xs"
          >
            <FolderInput size={13} /> Import existing folder…
          </button>
        </div>
      </div>
    </div>
  );
}
