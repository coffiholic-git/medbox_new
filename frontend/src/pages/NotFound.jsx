import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md pt-24 text-center">
      <p className="font-mono text-[12px] uppercase tracking-wide text-mint">404</p>
      <h1 className="mt-2 text-[28px] font-extrabold text-ink">We couldn't find that page.</h1>
      <p className="mt-2 text-[14px] text-muted">Let's get you back to something useful.</p>
      <Link to="/" className="mt-6 inline-block rounded-full bg-mint-dim px-6 py-3 text-[14px] font-bold text-navy-950 hover:bg-mint">
        Back home
      </Link>
    </div>
  );
}
