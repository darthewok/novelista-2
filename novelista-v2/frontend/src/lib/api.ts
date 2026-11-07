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
  chapters: { number: number; title: string | null; status: string; word_count: number; version: number; tells: number }[];
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

export type Provider = "anthropic" | "openai" | "openrouter" | "lmstudio" | "ollama";
export type Task = "outline" | "draft" | "revise" | "editor" | "foundation" | "voice" | "seed" | "summary" | "canon";
export type ProviderCfg = { api_key?: string | null; base_url?: string; num_ctx?: number };
export type Settings = {
  provider: Provider;
  providers: Record<string, ProviderCfg>;
  models: Record<Task, string>;
  quality: { auto_polish: boolean; max_polish_passes: number; tells_threshold: number };
};
export type SettingsPatch = {
  provider?: Provider;
  providers?: Record<string, ProviderCfg>;
  models?: Partial<Record<Task, string>>;
  quality?: Partial<Settings["quality"]>;
};
export type ConnectionTest = {
  provider: string | null; url: string | null; ok: boolean;
  models_present: Record<string, boolean>; available_models: string[]; error: string | null;
};
export type Finding = { rule: string; severity: "error" | "warning"; quote: string; line: number; message: string };
export type Report = {
  findings: Finding[]; error_count: number; warning_count: number;
  metrics: {
    word_count: number; sentence_count: number; paragraph_count: number; sentence_len_cv: number;
    paragraph_len_cv: number; em_dash_per_150: number; triad_count: number; transition_opener_ratio: number;
    tier1_count: number; tier2_repeats: number; dialogue_lines: number; adverb_tag_ratio: number; tells_per_1000: number;
  };
};
export type ArtifactKind = "world" | "characters" | "voice" | "canon";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!r.ok) {
    let msg = await r.text();
    try { const d = JSON.parse(msg)?.detail; if (d) msg = typeof d === "string" ? d : JSON.stringify(d); } catch {}
    throw new Error(`${r.status} ${msg}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}

async function uploadFile(id: string, file: File) {
  const fd = new FormData(); fd.append("file", file);
  const r = await fetch(`/api/books/${id}/uploads`, { method: "POST", body: fd });
  if (!r.ok) {
    let msg = await r.text();
    try { const d = JSON.parse(msg)?.detail; if (d) msg = typeof d === "string" ? d : JSON.stringify(d); } catch {}
    throw new Error(`${r.status} ${msg}`);
  }
  return r.json() as Promise<{ name: string; size: number; extracted_chars: number }>;
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
  getArtifact: (id: string, kind: ArtifactKind) => req<{ text: string }>(`/api/books/${id}/${kind}`),
  putArtifact: (id: string, kind: ArtifactKind, text: string) =>
    req<{ text: string }>(`/api/books/${id}/${kind}`, { method: "PUT", body: JSON.stringify({ text }) }),
  generateArtifact: (id: string, kind: ArtifactKind, body?: { choice?: number | null }) =>
    req<Job>(`/api/books/${id}/${kind}/generate`, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) }),
  // ponytail: voice-trial routes are a guess; backend has none yet.
  getVoiceTrials: (id: string) => req<{ text: string }>(`/api/books/${id}/voice/trials`),
  generateVoiceTrials: (id: string) => req<Job>(`/api/books/${id}/voice/trials`, { method: "POST" }),

  // Uploads
  uploadFile,
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
    req<{ number: number; title: string | null; status: string; word_count: number; version: number; tells: number }[]>(`/api/books/${id}/chapters`),
  getChapter: (id: string, n: number) =>
    req<{ number: number; title: string | null; status: string; word_count: number; version: number; text: string }>(`/api/books/${id}/chapters/${n}`),
  putChapter: (id: string, n: number, text: string) =>
    req<{ word_count: number; status: string }>(`/api/books/${id}/chapters/${n}`, { method: "PUT", body: JSON.stringify({ text }) }),
  draftChapter: (id: string, n: number, polish = false) =>
    req<Job>(`/api/books/${id}/chapters/${n}/draft`, { method: "POST", body: JSON.stringify({ polish }) }),
  reviseChapter: (id: string, n: number, notes: string, polish = false) =>
    req<Job>(`/api/books/${id}/chapters/${n}/revise`, { method: "POST", body: JSON.stringify({ notes, polish }) }),
  unacceptChapter: (id: string, n: number) =>
    req<{ status: string }>(`/api/books/${id}/chapters/${n}/unaccept`, { method: "POST" }),
  polishChapter: (id: string, n: number) => req<Job>(`/api/books/${id}/chapters/${n}/polish`, { method: "POST" }),
  editorChapter: (id: string, n: number) => req<Job>(`/api/books/${id}/chapters/${n}/editor`, { method: "POST" }),
  fixTells: (id: string, n: number) => req<Job>(`/api/books/${id}/chapters/${n}/fix-tells`, { method: "POST" }),
  tightenChapter: (id: string, n: number) => req<Job>(`/api/books/${id}/chapters/${n}/tighten`, { method: "POST" }),
  getReport: (id: string, n: number) => req<Report>(`/api/books/${id}/chapters/${n}/report`),
  getBrief: (id: string, n: number) => req<{ text: string }>(`/api/books/${id}/chapters/${n}/brief`),
  putBrief: (id: string, n: number, text: string) =>
    req<{ text: string }>(`/api/books/${id}/chapters/${n}/brief`, { method: "PUT", body: JSON.stringify({ text }) }),
  draftAll: (id: string, polish = false) =>
    req<{ job_ids: string[] }>(`/api/books/${id}/draft-all`, { method: "POST", body: JSON.stringify({ polish }) }),
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
  getSettings: () => req<Settings>("/api/settings"),
  putSettings: (body: SettingsPatch) => req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  testConnection: () => req<ConnectionTest>("/api/settings/test", { method: "POST" }),
};
