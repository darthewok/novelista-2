import { useEffect, useRef, useState } from "react";
import { useBlocker } from "react-router-dom";

/** Local text bound to server text. Server->local sync happens only when not dirty. */
export function useEditable(server: string | undefined) {
  const [text, setText] = useState("");
  const last = useRef<string | undefined>("");  // matches the initial local text so the first load syncs
  useEffect(() => {
    if (server === undefined) return;
    const prev = last.current;  // updater runs lazily; compare against the old server value
    last.current = server;
    setText((t) => (t === prev ? server : t));
  }, [server]);
  return { text, setText, dirty: server !== undefined && text !== server };
}

/** beforeunload + in-app navigation confirm while dirty. */
export function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("You have unsaved changes. Leave this page and discard them?")) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
}

/** Ctrl/Cmd+S. */
export function useSaveShortcut(save: () => void) {
  const ref = useRef(save);
  ref.current = save;
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); ref.current(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);
}

export function UnsavedBadge({ dirty }: { dirty: boolean }) {
  return dirty ? <span className="chip bg-amber-900/60 text-amber-200">Unsaved</span> : null;
}
