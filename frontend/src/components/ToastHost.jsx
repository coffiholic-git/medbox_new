import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info } from "lucide-react";
import { useStore } from "../store/useStore";

function ToastItem({ toast }) {
  const dismissToast = useStore((s) => s.dismissToast);
  useEffect(() => {
    const t = setTimeout(() => dismissToast(toast.id), 3800);
    return () => clearTimeout(t);
  }, [toast.id, dismissToast]);

  const Icon = toast.tone === "success" ? CheckCircle2 : Info;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.96 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      role="status"
      className="flex items-center gap-3 rounded-2xl border border-line bg-navy-800/95 px-5 py-4 text-sm font-semibold text-ink shadow-[0_18px_40px_rgba(0,0,0,0.4)] backdrop-blur"
    >
      <Icon size={18} className="shrink-0 text-mint" />
      <span>{toast.message}</span>
    </motion.div>
  );
}

export default function ToastHost() {
  const toasts = useStore((s) => s.toasts);
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4 sm:bottom-8"
    >
      <div className="flex w-full max-w-sm flex-col gap-2 pointer-events-auto">
        <AnimatePresence>
          {toasts.map((toast) => (
            <ToastItem key={toast.id} toast={toast} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
