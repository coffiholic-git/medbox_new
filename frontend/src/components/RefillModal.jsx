import { useState } from "react";
import { PackageCheck, ShoppingBag, Plus } from "lucide-react";
import Modal from "./Modal";
import { useStore } from "../store/useStore";
import { sound } from "../utils/audio";

export default function RefillModal({ open, onClose, medicine }) {
  const refillStock = useStore((s) => s.refillStock);
  const pushToast = useStore((s) => s.pushToast);
  const soundEnabled = useStore((s) => s.soundEnabled);
  const [refillQty, setRefillQty] = useState(30);

  if (!medicine) return null;

  const handleRefill = () => {
    refillStock(medicine.id, Number(refillQty));
    sound.playChime(soundEnabled);
    pushToast(`Added ${refillQty} units of ${medicine.name} to stock.`, "success");
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} labelledBy="refillTitle" width="max-w-md">
      <div className="text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-mint/20 text-mint">
          <PackageCheck size={24} />
        </div>
        <h2 id="refillTitle" className="mt-3 text-[22px] font-extrabold text-ink">
          Refill {medicine.name}
        </h2>
        <p className="mt-1 text-[13.5px] text-muted">
          Current stock: <strong className="text-mint">{medicine.stock || 0}</strong> / {medicine.maxStock || 30} units remaining.
        </p>

        <div className="mt-6 rounded-2xl border border-line bg-navy-800/60 p-4 text-left">
          <label className="block text-[12px] font-mono uppercase text-muted">Refill Quantity</label>
          <div className="mt-2 flex items-center gap-2">
            {[15, 30, 60, 90].map((qty) => (
              <button
                key={qty}
                onClick={() => setRefillQty(qty)}
                className={`flex-1 rounded-xl border py-2 text-[13px] font-bold transition ${
                  refillQty === qty ? "border-mint bg-mint-dim text-navy-950" : "border-line text-ink hover:border-mint/50"
                }`}
              >
                +{qty}
              </button>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-between text-[13px]">
            <span className="text-muted">Custom Amount:</span>
            <input
              type="number"
              min="1"
              max="200"
              value={refillQty}
              onChange={(e) => setRefillQty(Number(e.target.value))}
              className="w-24 rounded-lg border border-line bg-navy-900 px-3 py-1.5 font-mono text-right text-ink focus:border-mint focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-6 flex flex-col gap-2.5 sm:flex-row">
          <button
            onClick={() => {
              pushToast(`Pharmacy order placed for ${medicine.name}!`, "success");
              handleRefill();
            }}
            className="flex flex-1 items-center justify-center gap-2 rounded-full border border-line py-3 text-[13.5px] font-bold text-ink transition hover:border-mint hover:text-mint"
          >
            <ShoppingBag size={16} /> Express Pharmacy Order
          </button>
          <button
            onClick={handleRefill}
            className="flex-1 rounded-full bg-mint-dim py-3 text-[13.5px] font-bold text-navy-950 transition hover:bg-mint"
          >
            <Plus size={16} className="inline mr-1" /> Add to Cabinet
          </button>
        </div>
      </div>
    </Modal>
  );
}
