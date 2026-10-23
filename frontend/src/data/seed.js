// Seed data. In a real deployment this would come from the user's account
// and a proper medicine-identification service.

export const initialMedicines = [
  {
    id: "m-paracetamol",
    name: "Paracetamol",
    strength: "500 mg",
    form: "Tablet",
    frequency: "daily",
    time: "8:00 PM",
    instructions: "1 tablet · after dinner",
    color: "mint",
    offline: true,
    expiry: "Nov 2027",
    addedAt: "2026-06-02",
    stock: 4, // Intentionally low to demonstrate low-stock refill alert!
    maxStock: 30,
  },
  {
    id: "m-vitamind",
    name: "Vitamin D3",
    strength: "1000 IU",
    form: "Softgel",
    frequency: "weekly",
    time: "9:00 AM",
    instructions: "1 softgel · Sundays, with breakfast",
    color: "lime",
    offline: true,
    expiry: "Jan 2028",
    addedAt: "2026-05-14",
    stock: 18,
    maxStock: 60,
  },
  {
    id: "m-amlodipine",
    name: "Amlodipine",
    strength: "5 mg",
    form: "Tablet",
    frequency: "daily",
    time: "9:00 AM",
    instructions: "1 tablet · every morning",
    color: "coral",
    offline: true,
    expiry: "Mar 2027",
    addedAt: "2026-04-28",
    stock: 2, // Low stock alert demo
    maxStock: 30,
  },
];

// Simulated on-device recognition database used by the scan flow.
export const scanDatabase = [
  {
    name: "Amoxicillin",
    strength: "500 mg",
    form: "Capsule",
    confidence: 94,
    expiry: "Mar 2027",
    color: "mint",
    note: "Common antibiotic. Finish the full course even if you feel better.",
  },
  {
    name: "Ibuprofen",
    strength: "200 mg",
    form: "Tablet",
    confidence: 88,
    expiry: "Sep 2027",
    color: "lime",
    note: "Take with food to help protect your stomach.",
  },
  {
    name: "Metformin",
    strength: "850 mg",
    form: "Tablet",
    confidence: 91,
    expiry: "Jan 2028",
    color: "coral",
    note: "Usually taken with meals. Ask your pharmacist about timing.",
  },
  {
    name: "Cetirizine",
    strength: "10 mg",
    form: "Tablet",
    confidence: 79,
    expiry: "Jun 2027",
    color: "mint",
    note: "Antihistamine — may cause drowsiness in some people.",
  },
];

export const colorTokens = {
  mint: { bg: "bg-mint", text: "text-navy-950", ring: "ring-mint", soft: "bg-mint/15", border: "border-mint/40" },
  lime: { bg: "bg-lime", text: "text-navy-950", ring: "ring-lime", soft: "bg-lime/15", border: "border-lime/40" },
  coral: { bg: "bg-coral", text: "text-navy-950", ring: "ring-coral", soft: "bg-coral/15", border: "border-coral/40" },
};
