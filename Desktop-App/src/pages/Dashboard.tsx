import { Map, Cpu, Server, Upload, ArrowRight, CheckCircle2, Clock, XCircle, Pencil, Trash2, Check, MapPin } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAppStore } from "../lib/store";
import { cmd } from "../lib/tauri";
import { formatDate, cn } from "../lib/utils";

export function Dashboard() {
  const { profile, devices, regions, activeDeviceId, updateRegion, removeRegion } = useAppStore();
  const navigate = useNavigate();
  const activeDevice = devices.find((d) => d.id === activeDeviceId);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  const startEditName = (id: string, current: string) => {
    setEditingId(id);
    setEditingName(current);
  };

  const commitEditName = async (id: string) => {
    const trimmed = editingName.trim();
    if (!trimmed) { setEditingId(null); return; }
    const r = regions.find((x) => x.id === id);
    if (!r) { setEditingId(null); return; }
    const updated = { ...r, name: trimmed };
    updateRegion(updated);
    const next = regions.map((x) => (x.id === id ? updated : x));
    await cmd.saveRegions(next);
    setEditingId(null);
  };

  const deleteRegion = async (id: string) => {
    removeRegion(id);
    const next = regions.filter((x) => x.id !== id);
    await cmd.saveRegions(next);
  };

  const QUICK_ACTIONS = [
    { label: "Download Region", desc: "Select & fetch satellite tiles", icon: Map, to: "/maps", color: "cyan" },
    { label: "Manage Models", desc: "SuperPoint + LightGlue weights", icon: Cpu, to: "/models", color: "violet" },
    { label: "Manage Devices", desc: "Pi5 and local targets", icon: Server, to: "/devices", color: "emerald" },
    { label: "Upload to Device", desc: "Deploy maps and models", icon: Upload, to: "/upload", color: "amber" },
  ] as const;

  const COLOR_MAP = {
    cyan: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
    violet: "text-violet-400 bg-violet-500/10 border-violet-500/20",
    emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    amber: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  };

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-100">
          Good to see you, {profile?.name?.split(" ")[0] ?? "pilot"} 👋
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          {profile?.org ? `${profile.org} · ` : ""}Macula VPS Configuration
        </p>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-4 bg-bg-card border border-border rounded-xl px-5 py-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-400">Active device:</span>
          {activeDevice ? (
            <span className="badge-cyan">{activeDevice.name}</span>
          ) : (
            <span className="text-slate-500 text-xs">None selected</span>
          )}
        </div>
        <div className="w-px h-4 bg-border" />
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <span>{regions.length} region{regions.length !== 1 ? "s" : ""}</span>
        </div>
        <div className="w-px h-4 bg-border" />
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <span>{devices.length} device{devices.length !== 1 ? "s" : ""}</span>
        </div>
        <div className="ml-auto">
          <button onClick={() => navigate("/devices")} className="btn-ghost text-xs py-1 px-2">
            Manage <ArrowRight size={12} />
          </button>
        </div>
      </div>

      {/* Readiness checklist */}
      {(() => {
        const hasDevice = devices.length > 0;
        const hasActive = !!activeDeviceId;
        const hasRegion = regions.some((r) => r.last_downloaded);
        const checks = [
          { label: "Device configured", ok: hasDevice && hasActive, hint: !hasDevice ? "Add a device" : "Set active device", to: "/devices" },
          { label: "Region downloaded", ok: hasRegion, hint: "Download satellite tiles", to: "/maps" },
          { label: "Ready to deploy", ok: hasActive && hasRegion, hint: "Device + region needed", to: "/upload" },
        ];
        return (
          <div className="grid grid-cols-3 gap-3">
            {checks.map(({ label, ok, hint, to }) => (
              <button
                key={label}
                onClick={() => navigate(to)}
                className={cn(
                  "card text-left transition-all hover:border-border-strong",
                  ok ? "border-emerald-500/20" : "border-border"
                )}
              >
                <div className="flex items-center gap-2 mb-1">
                  {ok
                    ? <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                    : <XCircle size={13} className="text-slate-600 shrink-0" />}
                  <span className={cn("text-xs font-medium", ok ? "text-emerald-400" : "text-slate-400")}>
                    {label}
                  </span>
                </div>
                {!ok && <p className="text-[11px] text-slate-600 pl-[21px]">{hint} →</p>}
              </button>
            ))}
          </div>
        );
      })()}

      {/* Quick actions */}
      <div>
        <h2 className="section-title mb-3">Quick Actions</h2>
        <div className="grid grid-cols-2 gap-3">
          {QUICK_ACTIONS.map(({ label, desc, icon: Icon, to, color }) => (
            <button
              key={to}
              onClick={() => navigate(to)}
              className="card text-left hover:border-border-strong transition-all group flex items-start gap-4"
            >
              <div className={`w-10 h-10 rounded-lg border flex items-center justify-center shrink-0 ${COLOR_MAP[color]}`}>
                <Icon size={18} />
              </div>
              <div>
                <div className="font-medium text-slate-200 text-sm group-hover:text-white transition-colors">{label}</div>
                <div className="text-xs text-slate-500 mt-0.5">{desc}</div>
              </div>
              <ArrowRight size={14} className="text-slate-600 group-hover:text-slate-400 ml-auto mt-1 transition-colors" />
            </button>
          ))}
        </div>
      </div>

      {/* Recent regions */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="section-title">Saved Regions</h2>
          <button onClick={() => navigate("/maps")} className="btn-ghost text-xs py-1 px-2">
            + New region
          </button>
        </div>

        {regions.length === 0 ? (
          <div className="card text-center py-10">
            <Map size={32} className="text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400 text-sm">No regions yet</p>
            <p className="text-slate-500 text-xs mt-1">Draw a bounding box on the map to get started</p>
            <button onClick={() => navigate("/maps")} className="btn-primary mt-4 mx-auto">
              Open Map <ArrowRight size={14} />
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {regions.map((r) => (
              <div key={r.id} className="card group py-3 px-4 space-y-2">
                {/* Row 1: icon + name (editable) + date + actions */}
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shrink-0">
                    <Map size={14} className="text-cyan-400" />
                  </div>

                  {editingId === r.id ? (
                    <input
                      autoFocus
                      className="input-field flex-1 text-sm py-0.5 h-7"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEditName(r.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      onBlur={() => commitEditName(r.id)}
                    />
                  ) : (
                    <span className="flex-1 text-sm font-medium text-slate-200 truncate">{r.name}</span>
                  )}

                  <div className="flex items-center gap-1 shrink-0">
                    {editingId === r.id ? (
                      <button onClick={() => commitEditName(r.id)} className="btn-ghost py-1 px-1.5">
                        <Check size={12} className="text-emerald-400" />
                      </button>
                    ) : (
                      <button onClick={() => startEditName(r.id, r.name)} className="btn-ghost py-1 px-1.5 opacity-0 group-hover:opacity-100 hover:!opacity-100">
                        <Pencil size={11} />
                      </button>
                    )}
                    <button onClick={() => navigate("/upload")} className="btn-ghost py-1 px-1.5 text-xs">
                      <Upload size={12} />
                    </button>
                    <button onClick={() => deleteRegion(r.id)} className="btn-ghost py-1 px-1.5 text-red-400/60 hover:text-red-400">
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>

                {/* Row 2: metadata chips */}
                <div className="flex items-center gap-3 pl-11 flex-wrap">
                  {r.location_label && (
                    <span className="flex items-center gap-1 text-[11px] text-slate-400">
                      <MapPin size={10} className="text-cyan-500 shrink-0" />
                      {r.location_label}
                    </span>
                  )}
                  {!r.location_label && (
                    <span className="text-[11px] text-slate-500 font-mono">
                      {r.lat_min.toFixed(3)}, {r.lon_min.toFixed(3)}
                    </span>
                  )}
                  {r.gsd_m_per_px != null && (
                    <span className="text-[11px] text-slate-500">
                      <span className="text-slate-400 font-medium">{r.gsd_m_per_px.toFixed(2)} m/px</span>
                      {" "}resolution
                    </span>
                  )}
                  {r.file_size_mb != null && (
                    <span className="text-[11px] text-slate-500">
                      ~<span className="text-slate-400 font-medium">{r.file_size_mb.toFixed(0)} MB</span>
                    </span>
                  )}
                  {r.zoom && (
                    <span className="text-[10px] bg-bg-elevated border border-border rounded px-1.5 py-0.5 text-slate-500 font-mono">
                      Z{r.zoom}
                    </span>
                  )}
                  <div className="ml-auto">
                    {r.last_downloaded ? (
                      <div className="flex items-center gap-1.5 badge-green">
                        <CheckCircle2 size={10} />
                        {formatDate(r.last_downloaded)}
                      </div>
                    ) : (
                      <div className="badge-yellow">
                        <Clock size={10} />
                        Pending
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
