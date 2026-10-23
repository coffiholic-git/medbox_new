import { useState } from "react";
import { motion } from "framer-motion";
import { ShieldCheck, ScanLine, HeartPulse, Lock, Eye, EyeOff } from "lucide-react";
import { useStore } from "../store/useStore";
import { sound } from "../utils/audio";
import { loginAPI, registerAPI, googleAuthAPI } from "../utils/api";
import { signInWithGoogle } from "../config/firebase";

export default function AuthPage() {
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
  const [googleLoading, setGoogleLoading] = useState(false);

  const handleGoogleLogin = async () => {
    setGoogleLoading(true);
    sound.playClick(soundEnabled);
    try {
      // Step 1: real Google OAuth via Firebase (client-side).
      const googleProfile = await signInWithGoogle();

      // Step 2: exchange that verified identity for a MedBox backend JWT
      // — App.jsx only keeps a session that has a token, so without this
      // step the user would be signed straight back out.
      const result = await googleAuthAPI(googleProfile);

      if (!result || result._error || !result.access_token) {
        const detail = result?._detail || "Could not finish Google sign-in with the MedBox server.";
        pushToast(detail, "error");
        return;
      }

      const userProfile = {
        uid: result.uid,
        email: result.email,
        displayName: result.displayName,
        photoURL: googleProfile.photoURL,
        role: result.role,
        provider: "google",
      };

      setUser(userProfile, result.access_token);
      sound.playChime(soundEnabled);
      syncFromBackend();
      pushToast(`Signed in as ${userProfile.displayName || userProfile.email}. Welcome to MedBox!`, "success");
    } catch (err) {
      pushToast(err?.message || "Google sign-in failed.", "error");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    sound.playClick(soundEnabled);

    try {
      let result;

      if (mode === "register") {
        if (password.length < 8) {
          pushToast("Password must be at least 8 characters.", "error");
          return;
        }
        result = await registerAPI(name || "New Patient", email, password);
      } else {
        result = await loginAPI(email, password);
      }

      // Surface specific backend errors (422 validation, 400 duplicate, 401 wrong creds)
      if (!result || result._error) {
        const detail = result?._detail || "Authentication failed. Check your credentials and make sure the backend is running.";
        pushToast(detail, "error");
        return;
      }

      if (!result.access_token) {
        pushToast("Authentication failed. No token received.", "error");
        return;
      }

      const userProfile = {
        uid: result.uid,
        email: result.email,
        displayName: result.displayName,
        photoURL: null,
        role: result.role,
        provider: "email",
      };

      // setUser persists the JWT token so all subsequent API calls are authenticated.
      setUser(userProfile, result.access_token);
      sound.playChime(soundEnabled);

      // Load real data from the backend in the background — UI is already unlocked.
      syncFromBackend();

      const action = mode === "register" ? "Account created" : "Logged in";
      pushToast(`${action} as ${userProfile.displayName || userProfile.email}. Welcome to MedBox!`, "success");
    } catch (err) {
      pushToast("Authentication failed. Check your credentials.", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen text-ink flex items-center justify-center p-4 sm:p-6 overflow-hidden"
      style={{
        background: "rgba(4,6,15,0.4)",
        backdropFilter: "blur(2px)"
      }}
    >
      {/* Glowing background ambient lights */}
      <div className="ambient" style={{ width: 600, height: 600, background: "#3b82f6", top: -200, left: -180, opacity: 0.12 }} />
      <div className="ambient" style={{ width: 500, height: 500, background: "#8b5cf6", bottom: -120, right: -140, opacity: 0.14 }} />
      <div className="ambient" style={{ width: 380, height: 380, background: "#06b6d4", top: "30%", right: "20%", opacity: 0.08 }} />

      <div className="relative z-10 w-full max-w-4xl grid gap-8 lg:grid-cols-2 items-center">
        {/* Left Column: Brand & Feature Highlights */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="space-y-6"
        >
          <div className="flex items-center gap-3 text-[28px] font-extrabold tracking-tight text-ink">
            <span className="brand-gradient grid h-10 w-10 place-items-center rounded-xl text-2xl font-black text-white shadow-lg">+</span>
            med<span className="brand-gradient-text">box</span>
            <span className="rounded-full bg-mint/15 px-2.5 py-0.5 font-mono text-[11px] text-mint border border-mint/30">PRO</span>
          </div>

          <h1 className="text-[38px] font-extrabold leading-[1.1] tracking-tight text-ink sm:text-[46px]">
            Your AI Medical Companion & <span className="brand-gradient-text">Safety Station</span>
          </h1>

          <p className="text-[15px] leading-relaxed text-muted">
            Please sign in or create an account to unlock your personalized medication cabinet, camera OCR scanner, schedule matrix, and caregiver dashboard.
          </p>

          <div className="space-y-3 pt-2">
            {[
              { icon: ScanLine, text: "Smart AI Vision Pill Scanner & Label Reader" },
              { icon: ShieldCheck, text: "Real-Time Drug Interaction & Conflict Matrix" },
              { icon: HeartPulse, text: "Vitals Tracking & Remote Caregiver Monitoring" },
            ].map(({ icon: Icon, text }, i) => (
              <div key={i} className="flex items-center gap-3 text-[13.5px] font-bold text-ink">
                <span className="grid h-7 w-7 place-items-center rounded-lg shrink-0" style={{ background: "rgba(59,130,246,0.12)", border: "1px solid rgba(125,211,252,0.25)", color: "var(--color-mint)" }}>
                  <Icon size={15} />
                </span>
                {text}
              </div>
            ))}
          </div>
        </motion.div>

        {/* Right Column: High-Tech Auth Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[28px] p-6 sm:p-8 backdrop-blur-2xl shadow-2xl space-y-5"
          style={{
            background: "var(--glass-bg-bright)",
            border: "1px solid var(--glass-border-vivid)",
            boxShadow: "0 24px 64px -16px rgba(59,130,246,0.35), 0 4px 16px rgba(0,0,0,0.5), inset 0 1px 0 rgba(125,211,252,0.12)"
          }}
        >
          <div className="flex items-center justify-between">
            <div>
              <span className="font-mono text-[11px] uppercase tracking-wide text-mint">Secure Access</span>
              <h2 className="text-[22px] font-extrabold text-ink">
                {mode === "login" ? "Sign In to MedBox" : "Create Patient Account"}
              </h2>
            </div>
            <Lock size={20} className="text-mint opacity-80" />
          </div>

          {/* 1-Click Google OAuth */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={loading || googleLoading}
            className="flex w-full items-center justify-center gap-3 rounded-2xl border border-line bg-navy-900/90 py-3.5 text-[14px] font-bold text-ink transition hover:border-mint hover:bg-navy-900 disabled:opacity-50 shadow-md"
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
            {googleLoading ? "Connecting…" : "Continue with Google"}
          </button>

          <div className="relative flex items-center justify-center">
            <div className="w-full border-t border-line" />
            <span className="absolute bg-navy-800 px-3 font-mono text-[10.5px] uppercase text-muted">Or Credentials</span>
          </div>

          {/* Mode Switcher Tabs */}
          <div className="flex rounded-xl border border-line bg-navy-900/60 p-1">
            <button
              type="button"
              onClick={() => setMode("login")}
              className={`flex-1 py-2 text-[12.5px] font-bold rounded-lg transition ${
                mode === "login" ? "brand-gradient text-white" : "text-muted hover:text-ink"
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => setMode("register")}
              className={`flex-1 py-2 text-[12.5px] font-bold rounded-lg transition ${
                mode === "register" ? "brand-gradient text-white" : "text-muted hover:text-ink"
              }`}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5 pt-1">
            {mode === "register" && (
              <div>
                <label className="block text-[11px] font-mono uppercase text-muted">Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Maya Lin"
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
                  className="absolute right-3 top-3 text-muted hover:text-ink"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="brand-btn w-full rounded-full py-3.5 text-[14px] font-extrabold transition disabled:opacity-50 mt-2"
            >
              {loading ? "Authenticating…" : mode === "register" ? "Register & Enter Dashboard" : "Sign In & Unlock Dashboard"}
            </button>
          </form>
        </motion.div>
      </div>
    </div>
  );
}
