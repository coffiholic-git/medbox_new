import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useStore } from "../store/useStore";

export default function Modal({ open, onClose, title, labelledBy, children, width = "max-w-lg" }) {
  const reduceMotion = useStore((s) => s.reduceMotion);
  const panelRef = useRef(null);
  const closeRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement;
    closeRef.current?.focus();

    function onKeyDown(e) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusables = panelRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
      previouslyFocused?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-40 flex items-end justify-center sm:items-center">
          <motion.div
            className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.18 }}
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.section
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={labelledBy}
            className={`relative z-10 w-full ${width} max-h-[88vh] overflow-y-auto rounded-t-[28px] sm:rounded-[28px] border border-line bg-navy-800 p-7 shadow-[0_30px_90px_rgba(0,0,0,0.45)]`}
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 28 }}
            animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 18 }}
            transition={{ duration: reduceMotion ? 0 : 0.24, ease: [0.22, 1, 0.36, 1] }}
          >
            <button
              ref={closeRef}
              onClick={onClose}
              aria-label="Close dialog"
              className="absolute right-5 top-5 grid h-9 w-9 place-items-center rounded-full border border-line text-muted transition hover:border-mint hover:text-mint"
            >
              <X size={17} strokeWidth={2.2} />
            </button>
            {title && (
              <h2 id={labelledBy} className="pr-10 text-[26px] font-extrabold leading-tight tracking-tight text-ink">
                {title}
              </h2>
            )}
            <div className={title ? "mt-4" : ""}>{children}</div>
          </motion.section>
        </div>
      )}
    </AnimatePresence>
  );
}
