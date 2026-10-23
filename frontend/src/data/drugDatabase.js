// Comprehensive Drug Interaction, Food Safety & Patient Profiles Database

export const PATIENTS = [
  { id: "maya", name: "Maya Lin", relationship: "Visually Impaired Patient", age: 34, conditions: ["Visual Impairment / Blindness", "Hypertension"], caregiver: "Dr. Sarah Jenkins, MD" },
];

export const DRUG_INTERACTIONS = [
  {
    drugs: ["m-paracetamol", "Ibuprofen"],
    severity: "Moderate",
    title: "Dual NSAID / Analgesic Usage",
    description: "Avoid taking Paracetamol and Ibuprofen simultaneously without medical guidance to prevent elevated liver/kidney strain.",
  },
  {
    drugs: ["m-amlodipine", "Grapefruit Juice"],
    severity: "High",
    title: "Calcium Channel Blocker Conflict",
    description: "Grapefruit juice increases blood concentration of Amlodipine, which may cause sudden drops in blood pressure.",
  },
  {
    drugs: ["m-amlodipine", "Ibuprofen"],
    severity: "Moderate",
    title: "Blood Pressure Attenuation",
    description: "Ibuprofen may decrease the antihypertensive effect of Amlodipine and increase risk of renal impairment.",
  },
  {
    drugs: ["Amoxicillin", "m-paracetamol"],
    severity: "Low",
    title: "Monitored Intake",
    description: "No direct chemical conflict, but monitor for stomach discomfort when taking together.",
  },
];

export const FOOD_GUIDELINES = {
  "m-paracetamol": { food: "Take with water", warning: "Avoid excessive alcohol intake while taking paracetamol." },
  "m-vitamind": { food: "Take with meals containing fat", warning: "Vitamin D is fat-soluble; take with lunch or dinner for optimal absorption." },
  "m-amlodipine": { food: "Take morning or evening", warning: "Strictly avoid grapefruit or grapefruit juice." },
  "Amoxicillin": { food: "Take before or with meals", warning: "Complete the full course even if symptoms improve." },
  "Ibuprofen": { food: "Take with food or milk", warning: "Always consume with food to prevent gastric lining irritation." },
  "Metformin": { food: "Take with meals", warning: "Taking with food reduces stomach upset and diarrhea side-effects." },
};

export const SHAPE_TOKENS = {
  Tablet: { label: "Round Tablet", shape: "circle" },
  Capsule: { label: "Oblong Capsule", shape: "capsule" },
  Softgel: { label: "Oval Softgel", shape: "oval" },
  Liquid: { label: "Oral Solution", shape: "bottle" },
};
