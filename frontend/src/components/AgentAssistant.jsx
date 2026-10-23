import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { X, Send, Trash2 } from "lucide-react";
import { useStore } from "../store/useStore";
import { useSpeech } from "../hooks/useSpeech";
import { useAgentAssistant } from "../hooks/useAgentAssistant";
import { sound } from "../utils/audio";
import AgentOrb from "./AgentOrb";

/**
 * Floating "Ask MedBox" button + slide-over chat panel, mounted once in
 * Layout.jsx so it renders on every authenticated screen (Home, Scan,
 * Schedule, Safety, Library, Caregiver) instead of being Home-only.
 *
 * Gives two things the original Home-only widget didn't have:
 *   - A visible transcript (message bubbles), not just one status line.
 *   - A typed-text alternative to voice, for browsers without Web Speech
 *     support and for anyone who'd rather type.
 *
 * All the actual "talk to the backend" logic lives in
 * hooks/useAgentAssistant.js so this component and Home.jsx share one
 * conversation instead of keeping their own separate copies.
 */
export default function AgentAssistant() {
  const agentOpen = useStore((s) => s.agentOpen);
  const openAgent = useStore((s) => s.openAgent);
  const closeAgent = useStore((s) => s.closeAgent);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const hydrateAgentHistory = useStore((s) => s.hydrateAgentHistory);
  const clearAgentHistory = useStore((s) => s.clearAgentHistory);
  const pushToast = useStore((s) => s.pushToast);

  const { agentHistory, agentBusy, sendMessage } = useAgentAssistant();
  const navigate = useNavigate();
  const [draft, setDraft] = useState("");
  const [feedback, setFeedback] = useState("");
  const scrollRef = useRef(null);

  const { listen, speak, listening, supported } = useSpeech({
    onResult: (transcript) => handleSend(transcript),
    onError: (message) => setFeedback(message),
  });

  useEffect(() => {
    if (agentOpen) hydrateAgentHistory();
  }, [agentOpen, hydrateAgentHistory]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [agentHistory, agentOpen, agentBusy]);

  const handleSend = async (text) => {
    const trimmed = text?.trim();
    if (!trimmed) return;
    setDraft("");
    setFeedback("Thinking…");
    const reply = await sendMessage(trimmed, navigate);
    setFeedback("");
    if (reply) speak(reply);
  };

  const onSubmit = (e) => {
    e.preventDefault();
    handleSend(draft);
  };

  const onMic = () => {
    sound.playClick(soundEnabled);
    if (!supported) {
      setFeedback("Voice commands need Chrome or Edge with microphone permission enabled.");
      return;
    }
    setFeedback("Listening…");
    listen();
  };

  const onClear = async () => {
    await clearAgentHistory();
    pushToast("Assistant conversation cleared.");
  };

  return (
    <>
      {/* Floating launcher — visible on every screen this component is
          mounted on (see Layout.jsx), so the assistant isn't Home-only. */}
      {!agentOpen && (
        <motion.button
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => {
            sound.playClick(soundEnabled);
            openAgent();
          }}
          aria-label="Open MedBox AI assistant"
          className="fixed bottom-24 right-5 z-40 grid place-items-center rounded-full md:bottom-8"
        >
          <AgentOrb size={60} state="idle" />
        </motion.button>
      )}

      <AnimatePresence>
        {agentOpen && (
          <motion.div
            role="dialog"
            aria-label="MedBox AI assistant"
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="fixed bottom-4 right-4 z-40 flex h-[70vh] max-h-[560px] w-[92vw] max-w-sm flex-col overflow-hidden rounded-[22px] border border-line bg-navy-900/95 shadow-2xl backdrop-blur-xl md:bottom-8 md:right-8"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <AgentOrb size={36} state={agentBusy ? "thinking" : "idle"} />
                <div className="min-w-0">
                  <p className="text-[13px] font-extrabold text-ink">MedBox Assistant</p>
                  <p className="truncate text-[11px] text-muted" aria-live="polite">
                    {agentBusy ? "Thinking…" : feedback || "Ask about doses, stock, or interactions"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={onClear}
                  title="Clear conversation"
                  aria-label="Clear conversation"
                  className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-navy-800 hover:text-coral"
                >
                  <Trash2 size={15} />
                </button>
                <button
                  onClick={closeAgent}
                  title="Close"
                  aria-label="Close assistant"
                  className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-navy-800 hover:text-ink"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Transcript */}
            <div ref={scrollRef} className="flex-1 space-y-2.5 overflow-y-auto px-4 py-3">
              {agentHistory.length === 0 && (
                <p className="mt-6 text-center text-[12.5px] text-muted">
                  Try "What do I take next?" or "Do I have any low stock medicines?"
                </p>
              )}
              {agentHistory.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] leading-snug ${
                      m.role === "user"
                        ? "bg-mint-dim text-navy-950 font-medium"
                        : "border border-line bg-navy-800/70 text-ink"
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              ))}
              {agentBusy && (
                <div className="flex justify-start">
                  <div className="flex items-center gap-2 rounded-2xl border border-line bg-navy-800/70 px-3 py-2">
                    <AgentOrb size={20} state="thinking" />
                    <span className="text-[12px] text-muted">Thinking…</span>
                  </div>
                </div>
              )}
            </div>

            {/* Input row */}
            <form onSubmit={onSubmit} className="flex items-center gap-2 border-t border-line p-3">
              <button
                type="button"
                onClick={onMic}
                aria-label="Speak to the assistant"
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl"
              >
                {listening ? <AgentOrb size={34} state="listening" /> : <AgentOrb size={34} state="idle" />}
              </button>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Type a message…"
                aria-label="Type a message to the assistant"
                className="min-w-0 flex-1 rounded-xl border border-line bg-navy-950/60 px-3 py-2.5 text-[13px] text-ink outline-none focus:border-mint"
              />
              <button
                type="submit"
                disabled={!draft.trim() || agentBusy}
                aria-label="Send message"
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-line text-ink hover:border-mint hover:text-mint disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
