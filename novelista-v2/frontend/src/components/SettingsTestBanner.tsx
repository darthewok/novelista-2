import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** Footer banner: warns when the configured provider is unreachable or models are missing.
 * Refetches whenever Settings invalidates ["connection-test"].
 */
export function SettingsTestBanner() {
  const [dismissed, setDismissed] = useState(false);
  const { data, error } = useQuery({
    queryKey: ["connection-test"],
    queryFn: api.testConnection,
    retry: false,
    staleTime: Infinity,
  });

  let message = "";
  let bad = false;
  if (error) { message = (error as Error).message; bad = true; }
  else if (data && !data.ok) { message = data.error || "Cannot reach the provider. Check Settings."; bad = true; }
  else if (data) {
    const missing = Object.entries(data.models_present).filter(([, ok]) => !ok).map(([t]) => t);
    if (missing.length) message = `Models not found for: ${missing.join(", ")}. Check Settings.`;
  }

  if (dismissed || !message) return null;
  const color = bad ? "bg-red-950/80 border-red-900 text-red-200" : "bg-amber-950/80 border-amber-900 text-amber-200";
  return (
    <div className={`fixed bottom-4 right-4 left-4 md:left-auto md:max-w-md z-30 border rounded-lg px-4 py-3 backdrop-blur ${color}`}>
      <div className="flex items-start justify-between gap-3 text-sm">
        <div>{message}</div>
        <button className="text-xs opacity-70 hover:opacity-100" onClick={() => setDismissed(true)}>dismiss</button>
      </div>
    </div>
  );
}
