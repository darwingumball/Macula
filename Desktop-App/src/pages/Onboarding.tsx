import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ArrowLeft,
  Check,
  Server,
  HardDrive,
  Eye,
  EyeOff,
  Loader2,
  Wifi,
} from "lucide-react";
import { MaculaLogo } from "../App";
import { cmd } from "../lib/tauri";
import { useAppStore } from "../lib/store";
import { ACCENT_COLORS, cn, generateId } from "../lib/utils";
import type { Device, Profile } from "../lib/types";

type Step = "welcome" | "profile" | "device" | "done";

const STEPS: Step[] = ["welcome", "profile", "device", "done"];

export function Onboarding() {
  const [step, setStep] = useState<Step>("welcome");
  const { setProfile, addDevice } = useAppStore();
  const navigate = useNavigate();

  const [profile, setLocalProfile] = useState<Profile>({
    name: "",
    email: "",
    org: "",
    accent_color: ACCENT_COLORS[0],
    onboarding_complete: false,
  });

  const stepIdx = STEPS.indexOf(step);

  const next = () => setStep(STEPS[Math.min(stepIdx + 1, STEPS.length - 1)]);
  const back = () => setStep(STEPS[Math.max(stepIdx - 1, 0)]);

  const finish = async (device?: Device) => {
    const completed = { ...profile, onboarding_complete: true };
    await cmd.saveProfile(completed);
    setProfile(completed);
    if (device) {
      const devices = [device];
      await cmd.saveDevices(devices);
      addDevice(device);
    }
    navigate("/dashboard");
  };

  return (
    <div className="flex h-screen bg-bg-base items-center justify-center">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(#06B6D4 1px, transparent 1px), linear-gradient(90deg, #06B6D4 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative z-10 w-full max-w-lg px-6 animate-fade-in">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <MaculaLogo size={48} />
          <h1 className="mt-4 text-2xl font-bold text-slate-100">Macula</h1>
          <p className="text-slate-400 text-sm mt-1">Visual-Inertial Positioning for UAVs</p>
        </div>

        {/* Step indicator */}
        {step !== "welcome" && step !== "done" && (
          <div className="flex items-center gap-2 mb-6">
            {(["profile", "device"] as Step[]).map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <div
                  className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors",
                    s === step
                      ? "bg-cyan-500 text-white"
                      : stepIdx > STEPS.indexOf(s)
                      ? "bg-emerald-500 text-white"
                      : "bg-bg-elevated text-slate-500"
                  )}
                >
                  {stepIdx > STEPS.indexOf(s) ? <Check size={12} /> : i + 1}
                </div>
                <span
                  className={cn(
                    "text-xs",
                    s === step ? "text-slate-200" : "text-slate-500"
                  )}
                >
                  {s === "profile" ? "Profile" : "Device"}
                </span>
                {i === 0 && (
                  <div
                    className={cn(
                      "h-px w-8 mx-1 transition-colors",
                      stepIdx > 1 ? "bg-emerald-500" : "bg-border"
                    )}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {/* Step content */}
        <div className="card animate-slide-up">
          {step === "welcome" && (
            <WelcomeStep onNext={next} />
          )}
          {step === "profile" && (
            <ProfileStep
              profile={profile}
              onChange={setLocalProfile}
              onNext={next}
              onBack={back}
            />
          )}
          {step === "device" && (
            <DeviceStep onNext={next} onBack={back} onSkip={() => finish()} onFinishWithDevice={finish} />
          )}
          {step === "done" && (
            <DoneStep profile={profile} onFinish={() => finish()} />
          )}
        </div>
      </div>
    </div>
  );
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="text-center py-4">
      <h2 className="text-xl font-semibold text-slate-100 mb-2">Welcome to Macula</h2>
      <p className="text-slate-400 text-sm leading-relaxed mb-8">
        Configure satellite maps, manage AI models, and deploy to your drone hardware — all from one place.
      </p>
      <div className="grid grid-cols-3 gap-3 mb-8">
        {[
          { icon: "🗺️", label: "Satellite Maps", desc: "Download & manage flight regions" },
          { icon: "🧠", label: "AI Models", desc: "SuperPoint + LightGlue weights" },
          { icon: "📡", label: "Deploy to Pi5", desc: "One-click SSH upload" },
        ].map((f) => (
          <div key={f.label} className="bg-bg-surface rounded-lg p-3 text-center border border-border">
            <div className="text-2xl mb-1">{f.icon}</div>
            <div className="text-xs font-medium text-slate-200 mb-0.5">{f.label}</div>
            <div className="text-[10px] text-slate-500">{f.desc}</div>
          </div>
        ))}
      </div>
      <button onClick={onNext} className="btn-primary w-full justify-center">
        Get Started <ArrowRight size={15} />
      </button>
    </div>
  );
}

function ProfileStep({
  profile,
  onChange,
  onNext,
  onBack,
}: {
  profile: Profile;
  onChange: (p: Profile) => void;
  onNext: () => void;
  onBack: () => void;
}) {
  const valid = profile.name.trim().length > 0;

  return (
    <div>
      <h2 className="section-title mb-1">Create your profile</h2>
      <p className="text-slate-400 text-sm mb-6">Stored locally on this machine — no account required.</p>

      <div className="space-y-4">
        <div>
          <label className="label">Your name *</label>
          <input
            className="input-field"
            placeholder="e.g. Evan Schneider"
            value={profile.name}
            onChange={(e) => onChange({ ...profile, name: e.target.value })}
            autoFocus
          />
        </div>
        <div>
          <label className="label">Organization</label>
          <input
            className="input-field"
            placeholder="e.g. Drone Team / Solo"
            value={profile.org}
            onChange={(e) => onChange({ ...profile, org: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Email (optional)</label>
          <input
            className="input-field"
            type="email"
            placeholder="you@example.com"
            value={profile.email}
            onChange={(e) => onChange({ ...profile, email: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Accent color</label>
          <div className="flex gap-2 mt-1">
            {ACCENT_COLORS.map((c) => (
              <button
                key={c}
                onClick={() => onChange({ ...profile, accent_color: c })}
                className="w-7 h-7 rounded-full border-2 transition-all"
                style={{
                  background: c,
                  borderColor: profile.accent_color === c ? "white" : "transparent",
                  transform: profile.accent_color === c ? "scale(1.15)" : "scale(1)",
                }}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="flex gap-3 mt-6">
        <button onClick={onBack} className="btn-secondary">
          <ArrowLeft size={15} /> Back
        </button>
        <button onClick={onNext} className="btn-primary flex-1 justify-center" disabled={!valid}>
          Continue <ArrowRight size={15} />
        </button>
      </div>
    </div>
  );
}

function DeviceStep({
  onNext,
  onBack,
  onSkip,
  onFinishWithDevice,
}: {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
  onFinishWithDevice: (d: Device) => void;
}) {
  const [kind, setKind] = useState<"pi5" | "local" | null>(null);
  const [form, setForm] = useState({
    name: "My Pi5",
    host: "",
    port: 22,
    username: "pi",
    authMethod: "password" as "password" | "key",
    password: "",
    keyPath: "",
    remotePath: "/home/pi/Macula",
  });
  const [showPass, setShowPass] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const testConnection = async () => {
    if (!form.host) return;
    setTesting(true);
    setTestResult(null);
    try {
      const auth =
        form.authMethod === "password"
          ? { type: "Password" as const, password: form.password }
          : { type: "Key" as const, key_path: form.keyPath };
      const r = await cmd.testSshConnection(form.host, form.port, form.username, auth);
      setTestResult(r);
    } catch (e) {
      setTestResult({ ok: false, message: String(e) });
    } finally {
      setTesting(false);
    }
  };

  const saveDevice = () => {
    const auth =
      form.authMethod === "password"
        ? { type: "Password" as const, password: form.password }
        : { type: "Key" as const, key_path: form.keyPath };
    const device: Device = {
      id: generateId(),
      name: form.name,
      kind: kind === "pi5" ? "pi5" : "local",
      host: kind === "pi5" ? form.host : undefined,
      port: kind === "pi5" ? form.port : undefined,
      username: kind === "pi5" ? form.username : undefined,
      auth: kind === "pi5" ? auth : undefined,
      remote_project_path: kind === "pi5" ? form.remotePath : undefined,
    };
    onFinishWithDevice(device);
  };

  if (!kind) {
    return (
      <div>
        <h2 className="section-title mb-1">Add your first device</h2>
        <p className="text-slate-400 text-sm mb-6">You can add more devices later.</p>
        <div className="grid grid-cols-2 gap-3 mb-6">
          <button
            onClick={() => setKind("pi5")}
            className="card border-2 border-border hover:border-cyan-500/50 transition-colors text-left group"
          >
            <Server size={22} className="text-cyan-400 mb-3" />
            <div className="font-medium text-slate-200 text-sm mb-1">Raspberry Pi 5</div>
            <div className="text-xs text-slate-400">Upload via SSH to drone module</div>
          </button>
          <button
            onClick={() => setKind("local")}
            className="card border-2 border-border hover:border-cyan-500/50 transition-colors text-left group"
          >
            <HardDrive size={22} className="text-cyan-400 mb-3" />
            <div className="font-medium text-slate-200 text-sm mb-1">This Machine</div>
            <div className="text-xs text-slate-400">Save files locally for manual transfer</div>
          </button>
        </div>
        <div className="flex gap-3">
          <button onClick={onBack} className="btn-secondary">
            <ArrowLeft size={15} /> Back
          </button>
          <button onClick={onSkip} className="btn-ghost ml-auto text-sm">
            Skip for now
          </button>
        </div>
      </div>
    );
  }

  if (kind === "local") {
    return (
      <div>
        <h2 className="section-title mb-1">Local device</h2>
        <p className="text-slate-400 text-sm mb-6">
          Files will be saved to a folder you choose during upload.
        </p>
        <div className="mb-4">
          <label className="label">Device name</label>
          <input
            className="input-field"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="My Laptop"
          />
        </div>
        <div className="flex gap-3 mt-6">
          <button onClick={() => setKind(null)} className="btn-secondary">
            <ArrowLeft size={15} /> Back
          </button>
          <button onClick={saveDevice} className="btn-primary flex-1 justify-center">
            Save & Continue <ArrowRight size={15} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="section-title mb-1">Connect to Raspberry Pi 5</h2>
      <p className="text-slate-400 text-sm mb-5">SSH credentials — stored locally, never transmitted.</p>

      <div className="space-y-3">
        <div>
          <label className="label">Device name</label>
          <input className="input-field" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="col-span-2">
            <label className="label">IP address</label>
            <input className="input-field" placeholder="192.168.1.100" value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
          </div>
          <div>
            <label className="label">Port</label>
            <input className="input-field" type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} />
          </div>
        </div>
        <div>
          <label className="label">Username</label>
          <input className="input-field" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </div>
        <div>
          <label className="label">Auth method</label>
          <div className="flex gap-2">
            {(["password", "key"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setForm({ ...form, authMethod: m })}
                className={cn(
                  "flex-1 py-2 rounded-lg border text-sm font-medium transition-colors",
                  form.authMethod === m
                    ? "bg-cyan-500/10 border-cyan-500/40 text-cyan-400"
                    : "border-border text-slate-400 hover:border-border-strong"
                )}
              >
                {m === "password" ? "Password" : "SSH Key"}
              </button>
            ))}
          </div>
        </div>

        {form.authMethod === "password" ? (
          <div>
            <label className="label">Password</label>
            <div className="relative">
              <input
                className="input-field pr-10"
                type={showPass ? "text" : "password"}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              <button
                onClick={() => setShowPass(!showPass)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              >
                {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>
        ) : (
          <div>
            <label className="label">SSH key path</label>
            <input className="input-field" placeholder="~/.ssh/id_rsa" value={form.keyPath} onChange={(e) => setForm({ ...form, keyPath: e.target.value })} />
          </div>
        )}

        <div>
          <label className="label">Remote project path</label>
          <input className="input-field font-mono text-sm" value={form.remotePath} onChange={(e) => setForm({ ...form, remotePath: e.target.value })} />
        </div>

        {/* Test connection */}
        <button
          onClick={testConnection}
          disabled={!form.host || testing}
          className="btn-ghost w-full justify-center text-sm border border-border"
        >
          {testing ? <Loader2 size={14} className="animate-spin" /> : <Wifi size={14} />}
          {testing ? "Testing…" : "Test Connection"}
        </button>

        {testResult && (
          <div
            className={cn(
              "rounded-lg px-3 py-2 text-xs flex items-start gap-2",
              testResult.ok
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            )}
          >
            {testResult.ok ? <Check size={12} className="mt-0.5 shrink-0" /> : "✕"}
            {testResult.message}
          </div>
        )}
      </div>

      <div className="flex gap-3 mt-5">
        <button onClick={() => setKind(null)} className="btn-secondary">
          <ArrowLeft size={15} /> Back
        </button>
        <button
          onClick={saveDevice}
          disabled={!form.name || !form.host}
          className="btn-primary flex-1 justify-center"
        >
          Save & Finish <ArrowRight size={15} />
        </button>
      </div>
    </div>
  );
}

function DoneStep({ profile, onFinish }: { profile: Profile; onFinish: () => void }) {
  return (
    <div className="text-center py-4">
      <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto mb-4">
        <Check size={26} className="text-emerald-400" />
      </div>
      <h2 className="text-xl font-semibold text-slate-100 mb-2">
        You're all set, {profile.name.split(" ")[0]}!
      </h2>
      <p className="text-slate-400 text-sm mb-8">
        Head to <span className="text-cyan-400">Maps</span> to download your first flight region, or{" "}
        <span className="text-cyan-400">Models</span> to manage your AI weights.
      </p>
      <button onClick={onFinish} className="btn-primary w-full justify-center">
        Launch Macula <ArrowRight size={15} />
      </button>
    </div>
  );
}
