export function ErrorLine({ error }: { error?: string | null }) {
  return error ? <p role="alert" className="text-red-400 text-sm">{error}</p> : null;
}
