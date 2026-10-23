import { useState, useEffect } from "react";
import { Plus } from "lucide-react";
import Modal from "./Modal";
import { useStore } from "../store/useStore";

const emptyForm = {
  name: "",
  qualification: "",
  email: "",
  phone: "",
  relationship: "",
  assignedPatient: "",
};

export default function AddCaregiverModal({ open, onClose, caregiver = null }) {
  const addCaregiver = useStore((s) => s.addCaregiver);
  const updateCaregiver = useStore((s) => s.updateCaregiver);
  const pushToast = useStore((s) => s.pushToast);

  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (caregiver) {
      setForm({ ...emptyForm, ...caregiver });
    } else {
      setForm(emptyForm);
    }
  }, [caregiver, open]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.name.trim()) return;

    setSubmitting(true);
    const payload = {
      name: form.name.trim(),
      qualification: form.qualification.trim(),
      email: form.email.trim(),
      phone: form.phone.trim(),
      relationship: form.relationship.trim(),
      assignedPatient: form.assignedPatient.trim(),
    };

    try {
      if (caregiver?.id) {
        updateCaregiver(caregiver.id, payload);
        pushToast(`${payload.name} updated successfully.`, "success");
      } else {
        addCaregiver(payload);
        pushToast(`${payload.name} added as caregiver.`, "success");
      }
      onClose();
    } catch (err) {
      console.error(err);
      pushToast("Could not save caregiver. Please try again.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={caregiver ? "Edit Caregiver" : "Add Caregiver"}
      labelledBy="addCaregiverTitle"
      width="max-w-lg"
    >
      <form onSubmit={handleSubmit} className="mt-2 space-y-4">
        <p className="text-[13px] text-muted">
          {caregiver
            ? "Update caregiver contact and assignment details."
            : "Enter details for a new caregiver or physician."}
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Caregiver/Physician Name *">
            <input
              required
              autoFocus
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. Dr. Sarah Jenkins"
            />
          </Field>

          <Field label="Qualification/Designation">
            <input
              value={form.qualification}
              onChange={(e) => setForm({ ...form, qualification: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. MD, Nurse, Family"
            />
          </Field>

          <Field label="Email">
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. doctor@clinic.com"
            />
          </Field>

          <Field label="Phone Number">
            <input
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. +1 555-0199"
            />
          </Field>

          <Field label="Relationship/Role">
            <input
              value={form.relationship}
              onChange={(e) => setForm({ ...form, relationship: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. Primary Physician"
            />
          </Field>

          <Field label="Assigned Patient">
            <input
              value={form.assignedPatient}
              onChange={(e) => setForm({ ...form, assignedPatient: e.target.value })}
              className="w-full rounded-xl border border-line bg-navy-800/80 px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted focus:border-mint focus:outline-none"
              placeholder="e.g. Maya"
            />
          </Field>
        </div>

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
            {caregiver ? "Save Changes" : "Add Caregiver"}
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
