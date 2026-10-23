import { Mic } from "lucide-react";

export default function VoiceOrb({ listening, onClick, size = "large" }) {
  const dims = size === "large" ? "h-[172px] w-[172px]" : "h-14 w-14";
  return (
    <button
      onClick={onClick}
      aria-label="Start voice command"
      className={`group relative grid ${dims} place-items-center rounded-full border border-mint/40 bg-mint-dim text-navy-950 shadow-[0_0_0_10px_rgba(95,184,148,0.08),0_24px_60px_rgba(0,0,0,0.3)] transition-transform duration-200 hover:scale-[1.03] hover:bg-mint focus-visible:scale-[1.03] active:scale-[0.98] ${listening ? "listening" : ""}`}
    >
      {size === "large" && (
        <>
          <span className="ring-a pointer-events-none absolute inset-0 rounded-full border border-mint/50" />
          <span className="ring-b pointer-events-none absolute inset-0 rounded-full border border-mint/30" />
        </>
      )}
      <span className="relative flex flex-col items-center gap-2">
        {listening ? (
          <div className="flex items-center gap-1 h-8">
            <span className="w-1 bg-navy-950 rounded-full eq-bar-1" />
            <span className="w-1 bg-navy-950 rounded-full eq-bar-2" />
            <span className="w-1 bg-navy-950 rounded-full eq-bar-3" />
            <span className="w-1 bg-navy-950 rounded-full eq-bar-4" />
          </div>
        ) : (
          <Mic size={size === "large" ? 30 : 20} strokeWidth={2.2} />
        )}
        {size === "large" && (
          <span className="text-[13px] font-bold tracking-tight">
            {listening ? "Listening…" : "Tap to speak"}
          </span>
        )}
      </span>
    </button>
  );
}
