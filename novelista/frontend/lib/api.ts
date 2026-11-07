export type Book = {
  id: string;
  title: string;
  status: "draft" | "foundation" | "drafting" | "revising" | "complete";
  audience: "children" | "teen" | "adult" | null;
  book_type: "short_story" | "novel" | null;
  chapter_count: number | null;
  target_words: number | null;
  pov: "first_person" | "third_limited" | "third_omniscient" | null;
  writing_style:
    | "clinical" | "poetic" | "cyberpunk" | "anthropological" | "new_wave"
    | "high_epic" | "satirical" | "visceral" | "suburban_suspense" | "grindhouse_pulp"
    | null;
  idea: string | null;
  dir_path: string;
  created_at: string;
  updated_at: string;
  chapters: { id: string; number: number; title: string | null; status: string; word_count: number; version: number }[];
};

export type Job = {
  id: string;
  book_id: string | null;
  kind: string;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  created_at: string;
  finished_at: string | null;
  error: string | null;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}

export const api = {
  listBooks: () => req<Book[]>("/api/books"),
  getBook: (id: string) => req<Book>(`/api/books/${id}`),
  createBook: (body: Partial<Book>) => req<Book>("/api/books", { method: "POST", body: JSON.stringify(body) }),
  deleteBook: (id: string) => req<void>(`/api/books/${id}`, { method: "DELETE" }),
  patchBook: (id: string, body: Partial<Book>) => req<Book>(`/api/books/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  getSeed: (id: string) => req<{ text: string }>(`/api/books/${id}/seed`),
  putSeed: (id: string, text: string) => req<{ text: string }>(`/api/books/${id}/seed`, { method: "PUT", body: JSON.stringify({ text }) }),
  generateCandidates: (id: string) => req<Job>(`/api/books/${id}/seed/candidates`, { method: "POST" }),
  chooseSeed: (id: string, payload: { text?: string; index?: number }) =>
    req<{ text: string }>(`/api/books/${id}/seed/choose`, { method: "POST", body: JSON.stringify(payload) }),

  getJob: (id: string) => req<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => req<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST" }),

  // Foundation
  getArtifact: (id: string, kind: "world" | "characters" | "voice" | "canon") =>
    req<{ text: string }>(`/api/books/${id}/${kind}`),
  putArtifact: (id: string, kind: "world" | "characters" | "voice" | "canon", text: string) =>
    req<{ text: string }>(`/api/books/${id}/${kind}`, { method: "PUT", body: JSON.stringify({ text }) }),
  generateArtifact: (id: string, kind: "world" | "characters") =>
    req<Job>(`/api/books/${id}/${kind}/generate`, { method: "POST" }),

  // Uploads
  listUploads: (id: string) => req<{ files: { name: string; size: number }[]; has_extracted: boolean }>(`/api/books/${id}/uploads`),
  deleteUpload: (id: string, name: string) => req<void>(`/api/books/${id}/uploads/${encodeURIComponent(name)}`, { method: "DELETE" }),

  // Outline
  getOutline: (id: string) =>
    req<{ text: string; chapters: { number: number; title: string | null; status: string }[] }>(`/api/books/${id}/outline`),
  putOutline: (id: string, text: string) =>
    req<{ text: string; chapter_count: number }>(`/api/books/${id}/outline`, { method: "PUT", body: JSON.stringify({ text }) }),
  generateOutline: (id: string) =>
    req<Job>(`/api/books/${id}/outline/generate`, { method: "POST" }),

  // Chapters
  listChapters: (id: string) =>
    req<{ number: number; title: string | null; status: string; word_count: number; version: number }[]>(`/api/books/${id}/chapters`),
  getChapter: (id: string, n: number) =>
    req<{ number: number; title: string | null; status: string; word_count: number; version: number; text: string }>(`/api/books/${id}/chapters/${n}`),
  putChapter: (id: string, n: number, text: string) =>
    req<{ word_count: number; status: string }>(`/api/books/${id}/chapters/${n}`, { method: "PUT", body: JSON.stringify({ text }) }),
  draftChapter: (id: string, n: number) =>
    req<Job>(`/api/books/${id}/chapters/${n}/draft`, { method: "POST" }),
  reviseChapter: (id: string, n: number, notes: string) =>
    req<Job>(`/api/books/${id}/chapters/${n}/revise`, { method: "POST", body: JSON.stringify({ notes }) }),
  acceptChapter: (id: string, n: number) =>
    req<{ status: string }>(`/api/books/${id}/chapters/${n}/accept`, { method: "POST" }),
  evaluateChapter: (id: string, n: number) =>
    req<{ word_count: number; target_words: number | null; warnings: { severity: string; message: string; example: string }[] }>(`/api/books/${id}/chapters/${n}/evaluate`),
  listVersions: (id: string, n: number) =>
    req<{ current_version: number; versions: { version: number; path: string; word_count: number; current?: boolean }[] }>(`/api/books/${id}/chapters/${n}/versions`),
  getVersion: (id: string, n: number, v: number) =>
    req<{ version: number; text: string }>(`/api/books/${id}/chapters/${n}/versions/${v}`),

  // Export
  manuscriptUrl: (id: string) => `/api/books/${id}/manuscript`,
  exportZipUrl: (id: string) => `/api/books/${id}/export`,

  // Settings
  getSettings: () => req<{ ollama_url: string; model: string; default_chapter_count: number | null; default_target_words: number | null }>("/api/settings"),
  putSettings: (body: Partial<{ ollama_url: string; model: string; default_chapter_count: number | null; default_target_words: number | null }>) =>
    req<{ ollama_url: string; model: string }>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  testConnection: () => req<{ url: string; configured_model: string; model_present: boolean; available_models: string[] }>("/api/settings/test", { method: "POST" }),
};
