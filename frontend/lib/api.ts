/**
 * lib/api.ts
 * Typed API client — all backend calls go through here.
 * Handles: auth headers, error parsing, base URL.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API  = `${BASE}/api/v1`;

// ── Token management (localStorage in browser) ────────────────
export const token = {
  get: () => (typeof window !== "undefined" ? localStorage.getItem("access_token") : null),
  set: (t: string) => localStorage.setItem("access_token", t),
  clear: () => localStorage.removeItem("access_token"),
};

// ── Base fetcher ──────────────────────────────────────────────
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const tk = token.get();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (tk) headers["Authorization"] = `Bearer ${tk}`;
  if (!(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API}${path}`, { ...init, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error(err?.error?.message ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Types ─────────────────────────────────────────────────────
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface SourceReference {
  type: string;
  id: string;
  name: string;
  part_number?: string;
  relevance: number;
  url?: string;
  excerpt?: string;
}

export interface AgentResponse {
  session_id: string;
  message_id: string;
  content: string;
  sources: SourceReference[];
  confidence: number;
  tools_used: string[];
  latency_ms: number;
  needs_human_review: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceReference[];
  confidence?: number;
  latency_ms?: number;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  message_count: number;
}

export interface SearchResult {
  id: string;
  part_number: string;
  name: string;
  description?: string;
  category: string;
  brand?: string;
  price?: number;
  stock: number;
  in_stock: boolean;
  image_url?: string;
  relevance_score: number;
  match_type: string;
  specs: Record<string, unknown>;
  compatible_vehicles: Array<{ make: string; model: string; year_from: number; year_to: number }>;
}

export interface AnalyticsOverview {
  period_days: number;
  total_queries: number;
  avg_confidence: number | null;
  avg_latency_ms: number | null;
  feedback: { thumbs_up: number; thumbs_down: number; satisfaction_rate: number | null };
  knowledge_base: { documents_indexed: number; total_products: number };
}

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  status: string;
  chunk_count: number;
  size_bytes: number;
  created_at: string;
}

// ── Auth ──────────────────────────────────────────────────────
export const auth = {
  login: (email: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<UserResponse>("/auth/me"),
  register: (data: { email: string; password: string; full_name: string }) =>
    request<UserResponse>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
};

// ── Search ────────────────────────────────────────────────────
export const search = {
  byText: (query: string, filters?: { category?: string; brand?: string; max_price?: number }) =>
    request<{ query: string; results: SearchResult[]; result_count: number }>("/search/text", {
      method: "POST",
      body: JSON.stringify({ query, ...filters }),
    }),

  byImage: (file: File, vehicleFilters?: { make?: string; model?: string; year?: number }) => {
    const form = new FormData();
    form.append("file", file);
    if (vehicleFilters?.make)  form.append("vehicle_make", vehicleFilters.make);
    if (vehicleFilters?.model) form.append("vehicle_model", vehicleFilters.model);
    if (vehicleFilters?.year)  form.append("vehicle_year", String(vehicleFilters.year));
    return request<{ identified_part: Record<string, unknown>; results: SearchResult[]; result_count: number }>(
      "/search/image", { method: "POST", body: form }
    );
  },
};

// ── Chat ──────────────────────────────────────────────────────
export const chat = {
  send: (message: string, sessionId?: string, imageBase64?: string, imageMime?: string) =>
    request<AgentResponse>("/chat/message", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: sessionId ?? null,
        image_base64: imageBase64 ?? null,
        image_mime_type: imageMime ?? null,
      }),
    }),
  streamMessage: async function* (
    message: string,
    sessionId?: string,
    onEvent?: (event: string, data: any) => void,
  ) {
    const tk = token.get();
    const res = await fetch(`${API}/chat/message/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(tk ? { Authorization: `Bearer ${tk}` } : {}),
      },
      body: JSON.stringify({
        message,
        session_id: sessionId ?? null,
      }),
    });

    if (!res.ok || !res.body) {
      throw new Error(`Stream failed: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE 按 \n\n 分隔事件
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const evt of events) {
        if (!evt.trim()) continue;
        const lines = evt.split("\n");
        let eventName = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) data = line.slice(5).trim();
        }
        if (data) {
          try {
            const parsed = JSON.parse(data);
            onEvent?.(eventName, parsed);
            yield { event: eventName, data: parsed };
          } catch {}
        }
      }
    }
  },
  sessions: () => request<ChatSession[]>("/chat/sessions"),
  messages: (sessionId: string) => request<ChatMessage[]>(`/chat/sessions/${sessionId}`),
  feedback: (messageId: string, rating: "up" | "down", comment?: string) =>
    request("/chat/feedback", {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, rating, comment }),
    }),
};

// ── Admin ─────────────────────────────────────────────────────
export const admin = {
  overview: (days = 7) => request<AnalyticsOverview>(`/admin/analytics/overview?days=${days}`),
  failures: () => request<unknown[]>("/admin/analytics/failures"),
  topQueries: () => request<Array<{ query: string; count: number }>>("/admin/analytics/top-queries"),
  documents: () => request<Document[]>("/documents"),
  uploadDocument: (file: File, description = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("description", description);
    return request<{ document_id: string; task_id: string; status: string }>(
      "/documents/upload", { method: "POST", body: form }
    );
  },
  documentStatus: (id: string) => request<{ status: string; chunk_count: number; error_message?: string }>(
    `/documents/${id}/status`
  ),
  deleteDocument: (id: string) =>
    fetch(`${API}/documents/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token.get()}` },
    }),
};
