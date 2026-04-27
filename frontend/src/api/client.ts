/* Cliente HTTP base contra `/api/v1`. El proxy de Vite (vite.config.ts)
   redirige `/api` y `/ws` a `VITE_BACKEND_URL` (default http://localhost:8000).
   El bearer token se inyecta cuando esté disponible — placeholder en runtime. */

const BASE = "/api/v1";

let bearerToken: string | null = null;

export function setBearerToken(token: string | null): void {
  bearerToken = token;
}

interface FetchOptions extends RequestInit {
  query?: Record<string, string | number | boolean | undefined>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { query, headers, ...rest } = options;
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  const finalHeaders: Record<string, string> = {
    "content-type": "application/json",
    ...((headers as Record<string, string>) ?? {}),
  };
  if (bearerToken) finalHeaders.authorization = `Bearer ${bearerToken}`;

  const res = await fetch(url.toString().replace(window.location.origin, ""), {
    ...rest,
    headers: finalHeaders,
  });

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text().catch(() => null);
    }
    throw new ApiError(`HTTP ${res.status} ${res.statusText}`, res.status, body);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
