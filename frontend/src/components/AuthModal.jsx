import { useState } from "react";
import { LogIn, UserPlus, Shield, Eye, EyeOff, CheckCircle2 } from "lucide-react";
import Modal from "./Modal";
import { useStore } from "../store/useStore";
import { sound } from "../utils/audio";
import { loginAPI, registerAPI } from "../utils/api";

export default function AuthModal({ open, onClose }) {
  const setUser = useStore((s) => s.setUser);
  const syncFromBackend = useStore((s) => s.syncFromBackend);
  const pushToast = useStore((s) => s.pushToast);
  const soundEnabled = useStore((s) => s.soundEnabled);

  const [mode, setMode] = useState("login"); // login | register
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleGoogleLogin = async () => {
    setLoading(true);
    sound.playClick(soundEnabled);
    try {
      pushToast("Google sign-in is not configured. Please use your MedBox email and password.", "error");
    } catch (err) {
      pushToast("Google Sign-In failed.", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    sound.playClick(soundEnabled);

    try {
      const result = mode === "register"
        ? await registerAPI(name || "New Patient", email, password)
        : await loginAPI(email, password);
      if (!result?.access_token) throw new Error("Invalid credentials or backend unavailable");
      setUser({ uid: result.uid, email: result.email, displayName: result.displayName, role: result.role, provider: "email" }, result.access_token);
      await syncFromBackend();
      sound.playChime(soundEnabled);
      pushToast(mode === "register" ? `Account created for ${result.email}!` : `Logged in as ${result.displayName || result.email}.`, "success");
      onClose();
    } catch (err) {
      pushToast("Authentication failed. Check your credentials.", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} labelledBy="authTitle" width="max-w-md">
      <div className="text-left space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-mint text-navy-950 font-black">+</span>
            <div>
              <h2 id="authTitle" className="text-[20px] font-extrabold text-ink">
                MedBox Security Portal
              </h2>
              <p className="text-[12px] text-muted">Secure MedBox account sign-in</p>
            </div>
          </div>
          <span className="rounded-full bg-mint/20 px-2.5 py-0.5 font-mono text-[10px] text-mint border border-mint/30">
            SSL Secure
          </span>
        </div>

        {/* 1-Click Google OAuth Button */}
        <button
          type="button"
          onClick={handleGoogleLogin}
          disabled={loading}
          className="flex w-full items-center justify-center gap-3 rounded-xl border border-line bg-navy-900/90 py-3 text-[14px] font-bold text-ink transition hover:border-mint hover:bg-navy-900 disabled:opacity-50 shadow-md"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"
            />
            <path
              fill="#34A853"
              d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.27v3.15C3.25 21.3 7.31 24 12 24z"
            />
            <path
              fill="#FBBC05"
              d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.27C.46 8.2.01 10.04.01 12c0 1.96.45 3.8 1.26 5.42l4.01-3.15z"
            />
            <path
              fill="#EA4335"
              d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.25 2.7 1.27 6.58l4.01 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
            />
          </svg>
          Continue with Google
        </button>

        <div className="relative flex items-center justify-center my-4">
          <div className="w-full border-t border-line" />
          <span className="absolute bg-navy-950 px-3 font-mono text-[11px] uppercase text-muted">Or Email</span>
        </div>

        {/* Tab Selector */}
        <div className="flex rounded-xl border border-line bg-navy-900/60 p-1">
          <button
            type="button"
            onClick={() => setMode("login")}
            className={`flex-1 py-1.5 text-[12.5px] font-bold rounded-lg transition ${
              mode === "login" ? "bg-mint-dim text-navy-950" : "text-muted hover:text-ink"
            }`}
          >
            Log In
          </button>
          <button
            type="button"
            onClick={() => setMode("register")}
            className={`flex-1 py-1.5 text-[12.5px] font-bold rounded-lg transition ${
              mode === "register" ? "bg-mint-dim text-navy-950" : "text-muted hover:text-ink"
            }`}
          >
            Create Account
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3 pt-1">
          {mode === "register" && (
            <div>
              <label className="block text-[11px] font-mono uppercase text-muted">Full Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Dr. Maya Lin"
                className="input mt-1"
                required
              />
            </div>
          )}

          <div>
            <label className="block text-[11px] font-mono uppercase text-muted">Email Address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="patient@medbox.health"
              className="input mt-1"
              required
            />
          </div>

          <div>
            <label className="block text-[11px] font-mono uppercase text-muted">Password</label>
            <div className="relative mt-1">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="input pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-2.5 text-muted hover:text-ink"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-full bg-mint-dim py-3 text-[14px] font-bold text-navy-950 transition hover:bg-mint disabled:opacity-50 mt-4"
          >
            {loading ? "Authenticating…" : mode === "register" ? "Create MedBox Account" : "Sign In to Cabinet"}
          </button>
        </form>
      </div>
    </Modal>
  );
}
