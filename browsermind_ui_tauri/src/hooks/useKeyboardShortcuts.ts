import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCommandPaletteStore,
  useInspectorStore,
  useModeStore,
} from "@/stores";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

function isMod(e: KeyboardEvent): boolean {
  return e.metaKey || e.ctrlKey;
}

export function useKeyboardShortcuts() {
  const navigate = useNavigate();
  const paletteOpen = useCommandPaletteStore((s) => s.open);
  const togglePalette = useCommandPaletteStore((s) => s.toggle);
  const setPaletteOpen = useCommandPaletteStore((s) => s.setOpen);
  const toggleInspector = useInspectorStore((s) => s.toggle);
  const inspectorOpen = useInspectorStore((s) => s.open);
  const setInspectorOpen = useInspectorStore((s) => s.setOpen);
  const mode = useModeStore((s) => s.mode);
  const toggleMode = useModeStore((s) => s.toggle);
  const setMode = useModeStore((s) => s.setMode);

  const gTimerRef = useRef<number | null>(null);
  const gArmedRef = useRef(false);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) {
        if (e.key === "Escape") return;
        return;
      }

      // Cmd/Ctrl+K — toggle palette
      if (isMod(e) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        togglePalette();
        return;
      }

      // Cmd/Ctrl+\\ — toggle inspector
      if (isMod(e) && e.key === "\\") {
        e.preventDefault();
        toggleInspector();
        return;
      }

      // Cmd/Ctrl+Shift+D — toggle mode
      if (isMod(e) && e.shiftKey && (e.key === "d" || e.key === "D")) {
        e.preventDefault();
        const next = mode === "user" ? "developer" : "user";
        setMode(next);
        navigate(next === "developer" ? "/dev" : "/");
        return;
      }

      // Esc — close inspector when palette closed
      if (e.key === "Escape") {
        if (paletteOpen) return;
        if (inspectorOpen) {
          e.preventDefault();
          setInspectorOpen(false);
        }
        return;
      }

      // g-sequence chord
      if (e.key === "g" && !isMod(e) && !e.altKey && !e.shiftKey) {
        gArmedRef.current = true;
        if (gTimerRef.current !== null) {
          window.clearTimeout(gTimerRef.current);
        }
        gTimerRef.current = window.setTimeout(() => {
          gArmedRef.current = false;
          gTimerRef.current = null;
        }, 1000);
        return;
      }

      if (gArmedRef.current && !isMod(e) && !e.altKey) {
        const key = e.key.toLowerCase();
        let handled = true;
        switch (key) {
          case "h":
            navigate("/");
            break;
          case "w":
            navigate("/work");
            break;
          case "a":
            navigate("/accounts");
            break;
          case "s":
            navigate("/sessions");
            break;
          case "d":
            if (mode !== "developer") {
              toggleMode();
            }
            navigate("/dev");
            break;
          default:
            handled = false;
        }
        if (handled) {
          e.preventDefault();
        }
        gArmedRef.current = false;
        if (gTimerRef.current !== null) {
          window.clearTimeout(gTimerRef.current);
          gTimerRef.current = null;
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (gTimerRef.current !== null) {
        window.clearTimeout(gTimerRef.current);
        gTimerRef.current = null;
      }
    };
  }, [
    navigate,
    paletteOpen,
    togglePalette,
    setPaletteOpen,
    toggleInspector,
    inspectorOpen,
    setInspectorOpen,
    mode,
    toggleMode,
    setMode,
  ]);
}
