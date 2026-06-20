import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Save, FolderOpen, RefreshCw, ChevronDown, ChevronRight, Key } from "lucide-react";
import { cmd } from "../lib/tauri";
import { cn } from "../lib/utils";
import { useAppStore } from "../lib/store";

type YamlValue = string | number | boolean | null | YamlValue[] | Record<string, YamlValue>;

const SECTION_LABELS: Record<string, string> = {
  camera: "Camera",
  imu: "IMU",
  tracker: "Tracker",
  matcher: "Matcher",
  fix_quality: "Fix Quality",
  region_map: "Region Map",
  eskf: "ESKF",
  mavlink: "MAVLink",
  logging: "Logging",
};

const SECTION_COLORS: Record<string, string> = {
  camera: "text-cyan-400",
  imu: "text-violet-400",
  tracker: "text-emerald-400",
  matcher: "text-blue-400",
  fix_quality: "text-amber-400",
  region_map: "text-teal-400",
  eskf: "text-rose-400",
  mavlink: "text-orange-400",
  logging: "text-slate-400",
};

export function Settings() {
  const { profile, setProfile } = useAppStore();
  const [mapboxKey, setMapboxKey] = useState(profile?.mapbox_key ?? "");
  const [bingKey, setBingKey] = useState(profile?.bing_key ?? "");
  const [savingKeys, setSavingKeys] = useState(false);
  const [keysSaved, setKeysSaved] = useState(false);

  const [configPath, setConfigPath] = useState("");
  const [config, setConfig] = useState<Record<string, YamlValue> | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const saveKeys = async () => {
    if (!profile) return;
    setSavingKeys(true);
    setKeysSaved(false);
    const updated = {
      ...profile,
      mapbox_key: mapboxKey.trim() || undefined,
      bing_key: bingKey.trim() || undefined,
    };
    try {
      await cmd.saveProfile(updated);
      setProfile(updated);
      setKeysSaved(true);
      setTimeout(() => setKeysSaved(false), 2500);
    } catch (e) {
      setError(String(e));
    } finally {
      setSavingKeys(false);
    }
  };

  const loadConfig = async (path: string) => {
    try {
      const data = await cmd.readYamlConfig(path);
      setConfig(data as Record<string, YamlValue>);
      const init: Record<string, boolean> = {};
      Object.keys(data).forEach((k) => { init[k] = k === "camera" || k === "matcher"; });
      setExpanded(init);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };

  const pickConfig = async () => {
    const file = await open({
      filters: [{ name: "YAML config", extensions: ["yaml", "yml"] }],
      title: "Open params.yaml",
    });
    if (file) {
      setConfigPath(file as string);
      loadConfig(file as string);
    }
  };

  const saveConfig = async () => {
    if (!config || !configPath) return;
    setSaving(true);
    setSaved(false);
    try {
      await cmd.writeYamlConfig(configPath, config as Record<string, unknown>);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const updateValue = (section: string, key: string, raw: string) => {
    if (!config) return;
    const sectionData = config[section] as Record<string, YamlValue>;
    const existing = sectionData[key];
    let parsed: YamlValue = raw;
    if (typeof existing === "number") {
      parsed = Number(raw);
    } else if (typeof existing === "boolean") {
      parsed = raw === "true";
    } else if (Array.isArray(existing)) {
      try { parsed = JSON.parse(raw); } catch { parsed = raw; }
    }
    setConfig({
      ...config,
      [section]: { ...sectionData, [key]: parsed },
    });
    setSaved(false);
  };

  const toggle = (k: string) => setExpanded((e) => ({ ...e, [k]: !e[k] }));

  return (
    <div className="p-6 space-y-5 animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="section-title">Parameters</h1>
          <p className="text-slate-400 text-sm mt-1">Edit params.yaml or params_rpi5.yaml</p>
        </div>
        {config && (
          <button onClick={saveConfig} disabled={saving} className="btn-primary">
            {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
            {saved ? "Saved!" : "Save"}
          </button>
        )}
      </div>

      {/* API Keys */}
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Key size={14} className="text-cyan-400" /> API Keys
        </h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Mapbox API Key</label>
            <input
              className="input-field text-xs font-mono"
              type="password"
              value={mapboxKey}
              onChange={(e) => setMapboxKey(e.target.value)}
              placeholder="pk.eyJ1…"
            />
          </div>
          <div>
            <label className="label">Bing Maps API Key</label>
            <input
              className="input-field text-xs font-mono"
              type="password"
              value={bingKey}
              onChange={(e) => setBingKey(e.target.value)}
              placeholder="Bing key…"
            />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <p className="text-[11px] text-slate-500">Used for premium satellite layers in Maps</p>
          <button onClick={saveKeys} disabled={savingKeys || !profile} className="btn-secondary">
            {savingKeys ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
            {keysSaved ? "Saved!" : "Save Keys"}
          </button>
        </div>
      </div>

      {/* File picker */}
      <div className="flex gap-2">
        <input
          className="input-field flex-1 text-xs font-mono"
          value={configPath}
          onChange={(e) => setConfigPath(e.target.value)}
          placeholder="Path to params.yaml…"
          onKeyDown={(e) => e.key === "Enter" && configPath && loadConfig(configPath)}
        />
        <button onClick={pickConfig} className="btn-secondary px-3">
          <FolderOpen size={15} />
        </button>
        {configPath && (
          <button onClick={() => loadConfig(configPath)} className="btn-secondary px-3">
            <RefreshCw size={15} />
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-red-400 text-xs">
          {error}
        </div>
      )}

      {!config && !error && (
        <div className="card text-center py-12">
          <FolderOpen size={32} className="text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">Open a params.yaml to edit parameters</p>
          <button onClick={pickConfig} className="btn-primary mt-4 mx-auto">
            <FolderOpen size={14} /> Browse…
          </button>
        </div>
      )}

      {/* Config sections */}
      {config && (
        <div className="space-y-2">
          {Object.entries(config)
            .filter(([k]) => typeof config[k] === "object" && !Array.isArray(config[k]) && config[k] !== null)
            .map(([section, sectionVal]) => {
              const label = SECTION_LABELS[section] ?? section;
              const color = SECTION_COLORS[section] ?? "text-slate-400";
              const isOpen = expanded[section];
              const fields = Object.entries(sectionVal as Record<string, YamlValue>);
              return (
                <div key={section} className="card overflow-hidden p-0">
                  <button
                    onClick={() => toggle(section)}
                    className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-bg-elevated transition-colors text-left"
                  >
                    <span className={cn("text-sm font-semibold", color)}>{label}</span>
                    <span className="text-[10px] text-slate-500 ml-auto">{fields.length} params</span>
                    {isOpen ? <ChevronDown size={14} className="text-slate-500" /> : <ChevronRight size={14} className="text-slate-500" />}
                  </button>

                  {isOpen && (
                    <div className="border-t border-border px-5 py-4 grid grid-cols-2 gap-x-6 gap-y-3">
                      {fields.map(([key, val]) => (
                        <div key={key}>
                          <label className="label">{key}</label>
                          {typeof val === "boolean" ? (
                            <div className="flex gap-2">
                              {[true, false].map((b) => (
                                <button
                                  key={String(b)}
                                  onClick={() => updateValue(section, key, String(b))}
                                  className={cn(
                                    "flex-1 py-1.5 rounded-lg border text-xs font-medium transition-colors",
                                    val === b
                                      ? "bg-cyan-500/10 border-cyan-500/40 text-cyan-400"
                                      : "border-border text-slate-500"
                                  )}
                                >
                                  {String(b)}
                                </button>
                              ))}
                            </div>
                          ) : Array.isArray(val) ? (
                            <input
                              className="input-field text-xs font-mono"
                              value={JSON.stringify(val)}
                              onChange={(e) => updateValue(section, key, e.target.value)}
                            />
                          ) : (
                            <input
                              className="input-field text-sm"
                              type={typeof val === "number" ? "number" : "text"}
                              value={String(val ?? "")}
                              onChange={(e) => updateValue(section, key, e.target.value)}
                              step={typeof val === "number" && String(val).includes(".") ? "any" : undefined}
                            />
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
