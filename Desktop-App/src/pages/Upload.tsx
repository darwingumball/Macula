import { useState, useEffect } from "react";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { Upload as UploadIcon, Server, HardDrive, CheckCircle2, Loader2, FolderOpen, FileText, Map, Cpu } from "lucide-react";
import { cmd } from "../lib/tauri";
import { useAppStore } from "../lib/store";
import { cn } from "../lib/utils";
import type { Device, UploadProgress } from "../lib/types";

type UploadPayload = { file: string; bytes_sent: number; total_bytes: number; percent: number };

export function Upload() {
  const { devices, regions, activeDeviceId, setActiveDevice } = useAppStore();
  const activeDevice = devices.find((d) => d.id === activeDeviceId);

  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);

  useEffect(() => {
    const downloaded = regions.filter((r) => r.last_downloaded);
    if (downloaded.length > 0) {
      setSelectedFiles(
        downloaded.flatMap((r) => [
          `${r.output_path}/satellite.png`,
          `${r.output_path}/metadata.json`,
        ])
      );
    }
  }, []);
  const [remoteDir, setRemoteDir] = useState(activeDevice?.remote_project_path ?? "/home/pi/Macula");
  const [uploading, setUploading] = useState(false);
  const [fileProgress, setFileProgress] = useState<Record<string, number>>({});
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pickFiles = async () => {
    const files = await open({ multiple: true, title: "Select files to upload" });
    if (files) setSelectedFiles(Array.isArray(files) ? files : [files]);
  };

  const addRegionFiles = (regionOutputPath: string) => {
    const satellite = `${regionOutputPath}/satellite.png`;
    const meta = `${regionOutputPath}/metadata.json`;
    setSelectedFiles((f) => [...new Set([...f, satellite, meta])]);
  };

  const doUpload = async () => {
    if (!activeDevice || selectedFiles.length === 0) return;
    setUploading(true);
    setDone(false);
    setError(null);
    setFileProgress({});

    const unlisten = await listen<UploadPayload>("upload-progress", (e) => {
      setFileProgress((p) => ({ ...p, [e.payload.file]: e.payload.percent }));
    });

    try {
      if (activeDevice.kind === "pi5" && activeDevice.host && activeDevice.auth) {
        await cmd.sshUploadFiles(
          activeDevice.host,
          activeDevice.port ?? 22,
          activeDevice.username ?? "pi",
          activeDevice.auth,
          selectedFiles,
          remoteDir
        );
      }
      setDone(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
      unlisten();
    }
  };

  if (!activeDevice) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-full animate-fade-in">
        <Server size={40} className="text-slate-600 mb-4" />
        <h2 className="section-title mb-2">No device selected</h2>
        <p className="text-slate-400 text-sm text-center mb-6">
          Select a device from the sidebar or add one in the Devices page.
        </p>
        <div className="flex gap-3">
          {devices.map((d) => (
            <button
              key={d.id}
              onClick={() => setActiveDevice(d.id)}
              className="btn-secondary"
            >
              {d.kind === "pi5" ? <Server size={14} /> : <HardDrive size={14} />}
              {d.name}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="section-title">Upload to Device</h1>
        <p className="text-slate-400 text-sm mt-1">
          Deploy maps and models to{" "}
          <span className="text-cyan-400 font-medium">{activeDevice.name}</span>
          {activeDevice.kind === "pi5" && ` (${activeDevice.host})`}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* File selection */}
        <div className="space-y-4">
          <div className="card">
            <h3 className="text-sm font-medium text-slate-200 mb-3 flex items-center gap-2">
              <Map size={14} className="text-cyan-400" /> Add Region Files
            </h3>
            {regions.length === 0 ? (
              <p className="text-xs text-slate-500">No regions downloaded yet.</p>
            ) : (
              <div className="space-y-2">
                {regions.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => addRegionFiles(r.output_path)}
                    className={cn(
                      "w-full text-left flex items-center gap-3 rounded-lg border p-2.5 text-xs transition-colors",
                      selectedFiles.includes(`${r.output_path}/satellite.png`)
                        ? "border-cyan-500/40 bg-cyan-500/5 text-cyan-400"
                        : "border-border hover:border-border-strong text-slate-300"
                    )}
                  >
                    <Map size={13} className="shrink-0" />
                    <div>
                      <div className="font-medium">{r.name}</div>
                      <div className="text-slate-500 mt-0.5">{r.output_path}</div>
                    </div>
                    {selectedFiles.includes(`${r.output_path}/satellite.png`) && (
                      <CheckCircle2 size={12} className="ml-auto shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="text-sm font-medium text-slate-200 mb-3 flex items-center gap-2">
              <FolderOpen size={14} className="text-cyan-400" /> Browse Files
            </h3>
            <button onClick={pickFiles} className="btn-secondary w-full justify-center text-sm">
              <FolderOpen size={14} /> Pick files…
            </button>
          </div>
        </div>

        {/* Upload panel */}
        <div className="space-y-4">
          {/* Selected files */}
          <div className="card">
            <h3 className="text-sm font-medium text-slate-200 mb-3 flex items-center gap-2">
              <FileText size={14} className="text-cyan-400" />
              Files to Upload
              {selectedFiles.length > 0 && (
                <span className="badge-cyan ml-auto">{selectedFiles.length}</span>
              )}
            </h3>
            {selectedFiles.length === 0 ? (
              <p className="text-xs text-slate-500">No files selected.</p>
            ) : (
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {selectedFiles.map((f) => {
                  const name = f.split(/[\\/]/).pop() ?? f;
                  const pct = fileProgress[name];
                  return (
                    <div key={f} className="flex items-center gap-2 text-xs">
                      <FileText size={11} className="text-slate-500 shrink-0" />
                      <span className="flex-1 truncate text-slate-300 font-mono">{name}</span>
                      {pct !== undefined && (
                        <span className={cn("font-medium", pct >= 100 ? "text-emerald-400" : "text-cyan-400")}>
                          {pct.toFixed(0)}%
                        </span>
                      )}
                      <button
                        onClick={() => setSelectedFiles((fs) => fs.filter((x) => x !== f))}
                        className="text-slate-600 hover:text-red-400 ml-1"
                      >
                        ×
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Remote path (Pi5 only) */}
          {activeDevice.kind === "pi5" && (
            <div>
              <label className="label">Remote directory</label>
              <input
                className="input-field font-mono text-sm"
                value={remoteDir}
                onChange={(e) => setRemoteDir(e.target.value)}
              />
            </div>
          )}

          {/* Progress bars */}
          {uploading && Object.keys(fileProgress).length > 0 && (
            <div className="space-y-2">
              {Object.entries(fileProgress).map(([file, pct]) => (
                <div key={file}>
                  <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                    <span className="truncate font-mono">{file}</span>
                    <span>{pct.toFixed(0)}%</span>
                  </div>
                  <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full bg-cyan-500 rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {done && (
            <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2 text-emerald-400 text-sm">
              <CheckCircle2 size={15} /> Upload complete!
            </div>
          )}

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-red-400 text-xs">
              {error}
            </div>
          )}

          <button
            onClick={doUpload}
            disabled={selectedFiles.length === 0 || uploading}
            className="btn-primary w-full justify-center"
          >
            {uploading
              ? <><Loader2 size={15} className="animate-spin" /> Uploading…</>
              : <><UploadIcon size={15} /> Upload to {activeDevice.name}</>
            }
          </button>
        </div>
      </div>
    </div>
  );
}
