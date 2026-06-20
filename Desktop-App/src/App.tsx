import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { cmd } from "./lib/tauri";
import { useAppStore } from "./lib/store";
import { Onboarding } from "./pages/Onboarding";
import { Dashboard } from "./pages/Dashboard";
import { Maps } from "./pages/Maps";
import { Models } from "./pages/Models";
import { Devices } from "./pages/Devices";
import { Upload } from "./pages/Upload";
import { Settings } from "./pages/Settings";

export default function App() {
  const { setProfile, setDevices, setRegions, profile } = useAppStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([cmd.loadProfile(), cmd.loadDevices(), cmd.loadRegions()])
      .then(([p, d, r]) => {
        setProfile(p);
        setDevices(d);
        setRegions(r);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [setProfile, setDevices]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg-base">
        <div className="flex flex-col items-center gap-4 animate-fade-in">
          <MaculaLogo size={48} />
          <span className="text-slate-400 text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  const onboarded = profile?.onboarding_complete === true;

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/onboarding"
          element={onboarded ? <Navigate to="/dashboard" replace /> : <Onboarding />}
        />
        <Route
          path="/"
          element={
            onboarded ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <Navigate to="/onboarding" replace />
            )
          }
        />
        <Route
          element={
            onboarded ? <Layout /> : <Navigate to="/onboarding" replace />
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/maps" element={<Maps />} />
          <Route path="/models" element={<Models />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export function MaculaLogo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <circle cx="16" cy="16" r="15" stroke="#06B6D4" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="6" fill="#06B6D4" fillOpacity="0.15" stroke="#06B6D4" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="2.5" fill="#06B6D4" />
      <line x1="16" y1="1" x2="16" y2="8" stroke="#06B6D4" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="16" y1="24" x2="16" y2="31" stroke="#06B6D4" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="1" y1="16" x2="8" y2="16" stroke="#06B6D4" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="24" y1="16" x2="31" y2="16" stroke="#06B6D4" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
