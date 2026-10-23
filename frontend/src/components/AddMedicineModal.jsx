import { useState, useEffect } from "react";
import { Plus } from "lucide-react";
import Modal from "./Modal";
import { useStore } from "../store/useStore";
import { useSpeech } from "../hooks/useSpeech";

const emptyForm = {
  name: "",
  strength: "",
  form: "Tablet",
  frequency: "daily",
  time: "9:00 AM",
  instructions: "",
  stock: 30,
  maxStock: 30,
  expiry: "",
  color: "mint",
};

export default function AddMedicineModal({ open, onClose, medicine = null }) {
  const addMedicine = useStore((s) => s.addMedicine);
  const updateMedicine = useStore((s) => s.updateMedicine);
  const pushToast = useStore((s) => s.pushToast);
  const { speak } = useSpeech();

  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (medicine) {
      setForm({ ...emptyForm, ...medicine });
    } else {
      setForm(emptyForm);
    }
  }, [medicine, open]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.strength.trim()) return;

    setSubmitting(true);
    const instructions = form.instructions.trim() || `${form.form} · ${form.time}`;
    const payload = {
      ...form,
      color: form.color || "mint",
      name: form.name.trim(),
      strength: form.strength.trim(),
      instructions,
      stock: Number(form.stock) || 30,
      maxStock: Number(form.maxStock) || Math.max(30, Number(form.stock) || 30),
    };

    try {
      if (medicine?.id) {
        updateMedicine(medicine.id, payload);
        pushToast(`${payload.name} updated successfully.`, "success");
        speak?.(`${payload.name} was updated.`);
      } else {
        const advisory = await addMedicine(payload);
        if (advisory?.hasConflict) {
          pushToast(`${payload.name} added. ⚠️ Warning: ${advisory.advisoryMessage}`, "error");
          speak?.(`Medicine added, but note an advisory: ${advisory.advisoryMessage}`);
        } else {
          pushToast(`${payload.name} added to your pill cabinet.`, "success");
          speak?.(`${payload.name} was added to your medicine cabinet.`);
        }
      }
      onClose();
    } catch (err) {
      console.error(err);
      pushToast("Could not save medicine. Please try again.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={medicine ? "Edit Medicine" : "Add Medicine"}
      labelledBy="addMedicineTitle"
      width="max-w-lg"
    >
      <form onSubmit={handleSubmit} className="mt-2 space-y-4">
        <p className="text-[13px] text-muted">
          {medicine
            ? "Update prescription schedule, dosage, and inventory levels."
            : "Enter medicine details to schedule reminders, track doses, and check drug safety."}
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Medicine Name *">
            <input
              required
              autoFocus
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. Paracetamol"
            />
          </Field>

          <Field label="Strength / Dosage *">
            <input
              required
              value={form.strength}
              onChange={(e) => setForm({ ...form, strength: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. 500 mg"
            />
          </Field>

          <Field label="Form">
            <select
              value={form.form}
              onChange={(e) => setForm({ ...form, form: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink focus:border-mint focus:outline-none"
            >
              {["Tablet", "Capsule", "Softgel", "Liquid", "Injection", "Inhaler", "Drops"].map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Frequency">
            <select
              value={form.frequency}
              onChange={(e) => setForm({ ...form, frequency: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink focus:border-mint focus:outline-none"
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="asNeeded">As needed</option>
            </select>
          </Field>

          <Field label="Dose Time">
            <input
              value={form.time}
              onChange={(e) => setForm({ ...form, time: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. 8:00 PM"
            />
          </Field>

          <Field label="Pill Quantity / Stock">
            <input
              type="number"
              min="1"
              max="999"
              value={form.stock}
              onChange={(e) => setForm({ ...form, stock: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="30"
            />
          </Field>

          <div className="sm:col-span-2">
            <Field label="Expiry Date">
              <input
                value={form.expiry}
                onChange={(e) => setForm({ ...form, expiry: e.target.value })}
                className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
                placeholder="e.g. Dec 2027"
              />
            </Field>
          </div>
        </div>

        <Field label="Instructions (Optional)">
          <input
            value={form.instructions}
            onChange={(e) => setForm({ ...form, instructions: e.target.value })}
            className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
            placeholder="e.g. 1 tablet after meals with water"
          />
        </Field>

        <div className="flex gap-3 pt-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-xl border border-line py-2.5 text-[13.5px] font-bold text-ink hover:border-coral hover:text-coral transition"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-mint-dim py-2.5 text-[13.5px] font-bold text-navy-950 hover:bg-mint transition disabled:opacity-50"
          >
            <Plus size={16} strokeWidth={2.5} />
            {medicine ? "Save Changes" : "Add Medicine"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-bold text-muted">{label}</span>
      {children}
    </label>
  );
}
