import {
  LayoutDashboard,
  Map,
  Cpu,
  Server,
  Upload,
  Settings,
  ChevronRight,
  X,
  Minus,
  Square,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { MaculaLogo } from "../App";
import { useAppStore } from "../lib/store";
import { cn } from "../lib/utils";
import { getCurrentWindow } from "@tauri-apps/api/window";

const NAV = [
  { to: "/dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { to: "/maps", label: "Maps", Icon: Map },
  { to: "/models", label: "Models", Icon: Cpu },
  { to: "/devices", label: "Devices", Icon: Server },
  { to: "/upload", label: "Upload", Icon: Upload },
  { to: "/settings", label: "Settings", Icon: Settings },
];

export function Layout() {
  const { profile, devices, activeDeviceId, setActiveDevice } = useAppStore();
  const appWindow = getCurrentWindow();

  return (
    <div className="flex h-screen bg-bg-base overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex flex-col bg-bg-surface border-r border-border shrink-0">
        {/* Titlebar / Logo */}
        <div
          className="flex items-center gap-3 px-4 py-4 border-b border-border"
          data-tauri-drag-region
        >
          <MaculaLogo size={28} />
          <div>
            <div className="text-sm font-bold text-slate-100 leading-none">Macula</div>
            <div className="text-[10px] text-slate-500 mt-0.5">VPS Config</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg mb-0.5 text-sm font-medium transition-colors group",
                  isActive
                    ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
                    : "text-slate-400 hover:text-slate-200 hover:bg-bg-elevated"
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={16} className={isActive ? "text-cyan-400" : "text-slate-500 group-hover:text-slate-400"} />
                  {label}
                  {isActive && <ChevronRight size={12} className="ml-auto text-cyan-500" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Active device picker */}
        <div className="border-t border-border px-3 py-3">
          <div className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-2">
            Active Device
          </div>
          {devices.length === 0 ? (
            <NavLink to="/devices" className="text-xs text-cyan-400 hover:text-cyan-300">
              + Add device
            </NavLink>
          ) : (
            <select
              value={activeDeviceId ?? ""}
              onChange={(e) => setActiveDevice(e.target.value || null)}
              className="w-full bg-bg-elevated border border-border rounded-lg px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
            >
              <option value="">None selected</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Profile */}
        <div className="border-t border-border px-3 py-3 flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
            style={{ background: profile?.accent_color ?? "#06B6D4" }}
          >
            {profile?.name?.charAt(0)?.toUpperCase() ?? "?"}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium text-slate-200 truncate">{profile?.name}</div>
            <div className="text-[10px] text-slate-500 truncate">{profile?.org || "Macula"}</div>
          </div>
        </div>
      </aside>

      {/* Main content + custom title bar */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Custom title bar */}
        <div
          className="flex items-center justify-end h-9 px-3 bg-bg-base border-b border-border shrink-0"
          data-tauri-drag-region
        >
          <div className="flex items-center gap-1">
            <button
              onClick={() => appWindow.minimize()}
              className="w-7 h-7 flex items-center justify-center rounded hover:bg-bg-elevated text-slate-500 hover:text-slate-300 transition-colors"
            >
              <Minus size={12} />
            </button>
            <button
              onClick={() => appWindow.toggleMaximize()}
              className="w-7 h-7 flex items-center justify-center rounded hover:bg-bg-elevated text-slate-500 hover:text-slate-300 transition-colors"
            >
              <Square size={11} />
            </button>
            <button
              onClick={() => appWindow.close()}
              className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400 transition-colors"
            >
              <X size={13} />
            </button>
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
