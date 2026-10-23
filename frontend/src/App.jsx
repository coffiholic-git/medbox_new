import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Scan from "./pages/Scan";
import Schedule from "./pages/Schedule";
import Library from "./pages/Library";
import Caregiver from "./pages/Caregiver";
import Safety from "./pages/Safety";
import NotFound from "./pages/NotFound";
import AuthPage from "./pages/AuthPage";
import { useStore } from "./store/useStore";

export default function App() {
  const user = useStore((s) => s.user);
  const token = useStore((s) => s.token);
  const logoutUser = useStore((s) => s.logoutUser);
  const textSize = useStore((s) => s.textSize);
  const highContrast = useStore((s) => s.highContrast);
  const reduceMotion = useStore((s) => s.reduceMotion);

  useEffect(() => {
    document.documentElement.dataset.textsize = textSize;
  }, [textSize]);

  useEffect(() => {
    document.documentElement.dataset.contrast = highContrast ? "high" : "normal";
  }, [highContrast]);

  useEffect(() => {
    document.documentElement.dataset.motion = reduceMotion ? "reduced" : "normal";
  }, [reduceMotion]);

  // Discard legacy demo/Firebase sessions from earlier versions. Only a JWT
  // returned by the MedBox backend is now considered a signed-in session.
  useEffect(() => {
    if (user && !token) logoutUser();
  }, [user, token, logoutUser]);

  // If user is not authenticated, render full-screen Auth Landing Portal
  if (!user || !token) {
    return <AuthPage />;
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/scan" element={<Scan />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/library" element={<Library />} />
        <Route path="/caregiver" element={<Caregiver />} />
        <Route path="/safety" element={<Safety />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
