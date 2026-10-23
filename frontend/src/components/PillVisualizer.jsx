import { colorTokens } from "../data/seed";

export default function PillVisualizer({ form = "Tablet", color = "mint", size = "md" }) {
  const token = colorTokens[color] || colorTokens.mint;
  const isCapsule = form.toLowerCase().includes("capsule");
  const isSoftgel = form.toLowerCase().includes("softgel");
  const isLiquid = form.toLowerCase().includes("liquid");

  const dimensions = {
    sm: "w-8 h-8",
    md: "w-11 h-11",
    lg: "w-14 h-14",
  }[size] || "w-11 h-11";

  if (isLiquid) {
    return (
      <div className={`grid ${dimensions} place-items-center rounded-xl border ${token.border} ${token.soft}`}>
        <svg viewBox="0 0 24 24" fill="none" className="w-3/5 h-3/5" stroke="currentColor" strokeWidth="2">
          <path d="M9 3h6m-5 0v3m4-3v3M6 9h12v10a2 2 0 01-2 2H8a2 2 0 01-2-2V9z" />
          <path d="M6 13h12" strokeDasharray="2 2" />
        </svg>
      </div>
    );
  }

  if (isCapsule) {
    return (
      <div className={`grid ${dimensions} place-items-center rounded-xl border ${token.border} ${token.soft}`}>
        <div className="relative w-7 h-4 rounded-full border border-white/20 overflow-hidden flex transform -rotate-45 shadow-sm">
          <div className={`w-1/2 h-full ${token.bg}`} />
          <div className="w-1/2 h-full bg-navy-900 border-l border-white/20" />
        </div>
      </div>
    );
  }

  if (isSoftgel) {
    return (
      <div className={`grid ${dimensions} place-items-center rounded-xl border ${token.border} ${token.soft}`}>
        <div className={`w-6 h-4 rounded-full ${token.bg} opacity-90 shadow-inner transform rotate-12 flex items-center justify-center`}>
          <div className="w-2 h-1 bg-white/40 rounded-full blur-[1px]" />
        </div>
      </div>
    );
  }

  // Default: Tablet
  return (
    <div className={`grid ${dimensions} place-items-center rounded-xl border ${token.border} ${token.soft}`}>
      <div className={`relative w-6 h-6 rounded-full ${token.bg} flex items-center justify-center shadow-md`}>
        <div className="w-full h-[1px] bg-navy-950/40 transform rotate-45" />
      </div>
    </div>
  );
}
