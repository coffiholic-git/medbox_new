import { initializeApp, getApps } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut } from "firebase/auth";

// Real Firebase project config must come from the frontend's .env (see
// .env.example). There is no working fallback: an app can't authenticate
// against a Firebase project it isn't actually registered with, so if
// these aren't set we simply don't attempt the popup (see
// isFirebaseConfigured below) rather than pretending to succeed with a
// fake account, which is what silently broke Google sign-in before.
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const isFirebaseConfigured = Boolean(
  firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId && firebaseConfig.appId
);

// Only initialize the SDK when we have real config — initializing with
// empty/undefined values throws immediately and would crash the app on
// load for everyone who hasn't set up a Firebase project.
const app = isFirebaseConfigured ? (getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0]) : null;
export const auth = app ? getAuth(app) : null;
export const googleProvider = new GoogleAuthProvider();

/**
 * Google OAuth Sign In via Firebase.
 * Throws on any failure (no Firebase project configured, popup closed,
 * network error, etc.) — callers must catch and show the real error
 * instead of silently getting a fake account.
 * @returns {{uid, email, displayName, photoURL, provider:"google"}}
 */
export async function signInWithGoogle() {
  if (!isFirebaseConfigured) {
    throw new Error(
      "Google sign-in isn't set up yet: this deployment has no Firebase project configured. Add VITE_FIREBASE_* values to frontend/.env (see .env.example), or sign in with email and password instead."
    );
  }
  const res = await signInWithPopup(auth, googleProvider);
  return {
    uid: res.user.uid,
    email: res.user.email,
    displayName: res.user.displayName || res.user.email?.split("@")[0] || "Google User",
    photoURL: res.user.photoURL || null,
    provider: "google",
  };
}

// Sign Out (only relevant if a Google session via Firebase is active)
export async function logOutFirebase() {
  if (!auth) return;
  try {
    await signOut(auth);
  } catch (err) {
    console.warn("Firebase signout error:", err);
  }
}
