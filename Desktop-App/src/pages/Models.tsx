import { useState } from "react";
import { Cpu, Download, CheckCircle2, FolderOpen, Plus, Trash2, Star } from "lucide-react";
import { open } from "@tauri-apps/plugin-dialog";
import { cn, generateId } from "../lib/utils";
import type { ModelSet } from "../lib/types";

const DEFAULT_MODELS: ModelSet[] = [
  {
    id: "default",
    name: "SuperPoint v1 + LightGlue v0.1",
    superpoint_path: "weights/superpoint_v1.pth",
    lightglue_path: "weights/lightglue_v0.1_disk.pth",
    is_active: true,
    downloaded: false,
  },
];

const DOWNLOAD_URLS = {
  superpoint: "https://github.com/cvg/LightGlue/releases/download/v0.1_arxiv/superpoint_v1.pth",
  lightglue: "https://github.com/cvg/LightGlue/releases/download/v0.1_arxiv/lightglue_v0.1_disk.pth",
};

export function Models() {
  const [models, setModels] = useState<ModelSet[]>(DEFAULT_MODELS);
  const [adding, setAdding] = useState(false);
  const [newForm, setNewForm] = useState({ name: "", superpoint_path: "", lightglue_path: "" });

  const setActive = (id: string) =>
    setModels((m) => m.map((x) => ({ ...x, is_active: x.id === id })));

  const remove = (id: string) =>
    setModels((m) => m.filter((x) => x.id !== id || x.is_active));

  const pickFile = async (field: "superpoint_path" | "lightglue_path") => {
    const file = await open({
      multiple: false,
      filters: [{ name: "PyTorch weights", extensions: ["pth", "pt"] }],
    });
    if (file) setNewForm((f) => ({ ...f, [field]: file as string }));
  };

  const addModel = () => {
    if (!newForm.name || !newForm.superpoint_path || !newForm.lightglue_path) return;
    setModels((m) => [
      ...m,
      {
        id: generateId(),
        name: newForm.name,
        superpoint_path: newForm.superpoint_path,
        lightglue_path: newForm.lightglue_path,
        is_active: false,
        downloaded: true,
      },
    ]);
    setNewForm({ name: "", superpoint_path: "", lightglue_path: "" });
    setAdding(false);
  };

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="section-title">Model Sets</h1>
          <p className="text-slate-400 text-sm mt-1">
            SuperPoint + LightGlue weight pairs used by the VPS matcher.
          </p>
        </div>
        <button onClick={() => setAdding(true)} className="btn-primary">
          <Plus size={15} /> Add Model Set
        </button>
      </div>

      {/* Download hints */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2">
          <Download size={15} className="text-cyan-400" />
          <span className="text-sm font-medium text-slate-200">Official Weight Downloads</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(DOWNLOAD_URLS).map(([k, url]) => (
            <div key={k} className="bg-bg-surface border border-border rounded-lg p-3">
              <div className="text-xs font-medium text-slate-300 mb-1 capitalize">{k}</div>
              <div className="text-[10px] font-mono text-slate-500 truncate mb-2">{url.split("/").pop()}</div>
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="btn-ghost text-xs py-1 px-2 inline-flex"
              >
                <Download size={11} /> Open link
              </a>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-slate-500">
          Download weights, place in <code className="text-cyan-400 bg-bg-elevated px-1 rounded">weights/</code> in your Macula project folder, then add the model set below.
        </p>
      </div>

      {/* Model list */}
      <div className="space-y-3">
        {models.map((m) => (
          <div
            key={m.id}
            className={cn(
              "card flex items-center gap-4 transition-all",
              m.is_active && "border-cyan-500/30 bg-cyan-500/5"
            )}
          >
            <div className={cn(
              "w-10 h-10 rounded-lg border flex items-center justify-center shrink-0",
              m.is_active
                ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400"
                : "bg-bg-elevated border-border text-slate-500"
            )}>
              <Cpu size={17} />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-200">{m.name}</span>
                {m.is_active && <span className="badge-cyan"><Star size={9} /> Active</span>}
              </div>
              <div className="text-[11px] font-mono text-slate-500 mt-0.5 space-y-0.5">
                <div>SP: {m.superpoint_path}</div>
                <div>LG: {m.lightglue_path}</div>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {m.downloaded ? (
                <span className="badge-green"><CheckCircle2 size={10} /> Ready</span>
              ) : (
                <span className="badge-yellow">Not downloaded</span>
              )}
              {!m.is_active && (
                <button
                  onClick={() => setActive(m.id)}
                  className="btn-secondary text-xs py-1 px-3"
                >
                  Set Active
                </button>
              )}
              {!m.is_active && models.length > 1 && (
                <button
                  onClick={() => remove(m.id)}
                  className="btn-ghost text-red-400 hover:text-red-300 py-1 px-2"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Add form */}
      {adding && (
        <div className="card border-cyan-500/20 space-y-4">
          <h3 className="text-sm font-semibold text-slate-200">Add Custom Model Set</h3>
          <div>
            <label className="label">Name</label>
            <input
              className="input-field"
              value={newForm.name}
              onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. SuperPoint v2 Custom"
            />
          </div>
          <div>
            <label className="label">SuperPoint weights (.pth)</label>
            <div className="flex gap-2">
              <input className="input-field flex-1 text-xs font-mono" value={newForm.superpoint_path} readOnly placeholder="Select file…" />
              <button onClick={() => pickFile("superpoint_path")} className="btn-secondary px-3">
                <FolderOpen size={14} />
              </button>
            </div>
          </div>
          <div>
            <label className="label">LightGlue weights (.pth)</label>
            <div className="flex gap-2">
              <input className="input-field flex-1 text-xs font-mono" value={newForm.lightglue_path} readOnly placeholder="Select file…" />
              <button onClick={() => pickFile("lightglue_path")} className="btn-secondary px-3">
                <FolderOpen size={14} />
              </button>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setAdding(false)} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button
              onClick={addModel}
              disabled={!newForm.name || !newForm.superpoint_path || !newForm.lightglue_path}
              className="btn-primary flex-1 justify-center"
            >
              Add Set
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
