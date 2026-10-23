import { useCallback, useEffect, useRef, useState } from "react";

const SpeechRecognitionImpl =
  typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

export function useSpeech({ onResult, onError } = {}) {
  const [listening, setListening] = useState(false);
  const [supported] = useState(!!SpeechRecognitionImpl);
  const recognitionRef = useRef(null);
  const onResultRef = useRef(onResult);
  const onErrorRef = useRef(onError);
  onResultRef.current = onResult;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!SpeechRecognitionImpl) return;
    const recognition = new SpeechRecognitionImpl();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      onResultRef.current?.(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = (event) => {
      setListening(false);
      const messages = {
        "not-allowed": "Microphone access was blocked. Allow microphone permission and try again.",
        "no-speech": "I did not hear anything. Please try again.",
        "network": "Voice recognition needs an internet connection in this browser.",
      };
      onErrorRef.current?.(messages[event.error] || "Voice recognition could not start. Please try again.");
    };
    recognitionRef.current = recognition;
    return () => recognition.abort();
  }, []);

  const speak = useCallback((text) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.98;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }, []);

  const listen = useCallback(async () => {
    if (!recognitionRef.current) {
      onErrorRef.current?.("Voice commands require Chrome or Edge with microphone permission enabled.");
      return false;
    }
    try {
      // Ask for microphone permission explicitly. Web Speech alone often
      // fails silently when a browser has never been allowed to use the mic.
      if (navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
      }
      setListening(true);
      recognitionRef.current.start();
      return true;
    } catch {
      setListening(false);
      onErrorRef.current?.("Microphone permission was not granted, or voice recognition is unavailable. Allow microphone access in your browser and try again.");
      return false;
    }
  }, []);

  return { listen, speak, listening, supported };
}
