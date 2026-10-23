import { useMemo, useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Search, Plus, Pill } from "lucide-react";
import { useStore } from "../store/useStore";
import { useSpeech } from "../hooks/useSpeech";
import MedicineCard from "../components/MedicineCard";
import Modal from "../components/Modal";
import AddMedicineModal from "../components/AddMedicineModal";

const filters = [
  { id: "all", label: "All" },
  { id: "daily", label: "Daily" },
  { id: "weekly", label: "Weekly" },
  { id: "asNeeded", label: "As needed" },
];

export default function Library() {
  const medicines = useStore((s) => s.medicines);
  const removeMedicine = useStore((s) => s.removeMedicine);
  const pushToast = useStore((s) => s.pushToast);
  const { speak } = useSpeech();
  const [searchParams] = useSearchParams();

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [formOpen, setFormOpen] = useState(false);
  const [editingMedicine, setEditingMedicine] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  useEffect(() => {
    if (searchParams.get("add") === "true") {
      setEditingMedicine(null);
      setFormOpen(true);
    }
  }, [searchParams]);

  const filtered = useMemo(() => {
    return medicines.filter((m) => {
      const matchesQuery = `${m.name} ${m.strength}`.toLowerCase().includes(query.toLowerCase());
      const matchesFilter = filter === "all" || m.frequency === filter;
      return matchesQuery && matchesFilter;
    });
  }, [medicines, query, filter]);

  const openAdd = () => {
    setEditingMedicine(null);
    setFormOpen(true);
  };

  const openEdit = (medicine) => {
    setEditingMedicine(medicine);
    setFormOpen(true);
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    await removeMedicine(confirmDelete.id);
    pushToast(`${confirmDelete.name} was removed.`);
    setConfirmDelete(null);
  };

  return (
    <div className="pt-6 space-y-6">
      {/* Pill Cabinet Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full px-2.5 py-1 font-mono text-[10.5px] text-mint" style={{ background: "rgba(125,211,252,0.07)", border: "1px solid rgba(125,211,252,0.2)" }}>
            <Pill size={12} className="text-mint" />
            PILL CABINET · {medicines.length} MEDICATIONS
          </div>
          <h1 className="mt-1 text-[30px] font-extrabold tracking-tight text-ink sm:text-[34px]">
            Pill Cabinet
          </h1>
          <p className="text-[13.5px] text-muted">
            Manage your prescription library, dosing frequency, and inventory stock.
          </p>
        </div>

        {/* Add Medicine Button inside Pill Cabinet */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          id="pill-cabinet-add-medicine-btn"
          onClick={openAdd}
          className="flex items-center gap-2 rounded-2xl bg-mint px-5 py-2.5 text-[13.5px] font-extrabold text-navy-950 shadow-[0_0_20px_rgba(45,212,191,0.25)] transition hover:brightness-105"
        >
          <Plus size={17} strokeWidth={2.5} />
          <span>Add Medicine</span>
        </motion.button>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search medications by name or dosage..."
            aria-label="Search medications"
            className="w-full rounded-2xl border border-line bg-navy-800/60 py-3 pl-11 pr-4 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
          />
        </div>
        <div className="flex gap-1.5 overflow-x-auto scrollbar-none">
          {filters.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`shrink-0 rounded-xl border px-3.5 py-2 text-[12.5px] font-bold transition ${
                filter === f.id
                  ? "border-mint bg-mint text-navy-950 font-extrabold shadow-sm"
                  : "border-line text-muted hover:border-mint/50 hover:text-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Medicine Cards List */}
      <div className="space-y-3">
        <AnimatePresence initial={false}>
          {filtered.map((m, i) => (
            <MedicineCard
              key={m.id}
              medicine={m}
              index={i}
              onSpeak={speak}
              onEdit={openEdit}
              onDelete={setConfirmDelete}
            />
          ))}
        </AnimatePresence>

        {filtered.length === 0 && (
          <div className="rounded-2xl border border-line bg-navy-800/40 p-10 text-center">
            <p className="text-[15px] font-bold text-ink">No medicines match your search.</p>
            <p className="mt-1 text-[13.5px] text-muted">Try a different search term or add a new medicine to your cabinet.</p>
            <button
              onClick={openAdd}
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-mint px-4 py-2 text-[13px] font-extrabold text-navy-950 hover:brightness-105 transition"
            >
              <Plus size={15} strokeWidth={2.5} /> Add Medicine
            </button>
          </div>
        )}
      </div>

      {/* Add / Edit Medicine Modal */}
      <AddMedicineModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        medicine={editingMedicine}
      />

      {/* Confirm Delete Modal */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Remove this medicine?" labelledBy="deleteTitle" width="max-w-sm">
        {confirmDelete && (
          <div>
            <p className="text-[14px] text-muted">
              {confirmDelete.name} {confirmDelete.strength} will be removed from your library and schedule.
            </p>
            <div className="mt-6 flex gap-2.5">
              <button
                onClick={() => setConfirmDelete(null)}
                className="flex-1 rounded-full border border-line py-3 text-[14px] font-bold text-ink hover:border-mint hover:text-mint"
              >
                Keep it
              </button>
              <button onClick={doDelete} className="flex-1 rounded-full bg-coral py-3 text-[14px] font-bold text-navy-950 hover:brightness-110">
                Remove
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
