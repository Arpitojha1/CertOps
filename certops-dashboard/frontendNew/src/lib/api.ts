/**
 * frontendNew/src/lib/api.ts
 *
 * HTTP client for CertOps API using native fetch.
 * - credentials: "include" → automatically sends the httpOnly `certops_token` cookie
 * - 401 handling           → redirects to /pricing on session expiry
 * - X-Tenant-Id header     → injected from localStorage once obtained via /auth/me
 */

const BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const tenantId = localStorage.getItem("certops_tenant_id");
  if (tenantId && !headers.has("X-Tenant-Id")) {
    headers.set("X-Tenant-Id", tenantId);
  }

  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (response.status === 401) {
    localStorage.removeItem("certops_tenant_id");
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized (401)");
  }

  if (!response.ok) {
    let errorData: unknown;
    try {
      errorData = await response.json();
    } catch {
      errorData = await response.text();
    }
    const error = new Error(`HTTP error ${response.status}: ${response.statusText}`);
    Object.assign(error, { status: response.status, response: { status: response.status, data: errorData } });
    throw error;
  }

  if (response.status === 204 || response.headers.get("Content-Length") === "0") {
    return {} as T;
  }

  try {
    return await response.json();
  } catch {
    return (await response.text()) as unknown as T;
  }
}

export async function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  let urlPath = path;
  if (params && Object.keys(params).length > 0) {
    const searchParams = new URLSearchParams();
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      urlPath += (path.includes("?") ? "&" : "?") + queryString;
    }
  }
  return request<T>(urlPath, { method: "GET" });
}

export async function apiPost<T, B = unknown>(path: string, body?: B): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function apiPut<T, B = unknown>(path: string, body?: B): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export default {
  get: apiGet,
  post: apiPost,
  put: apiPut,
  delete: apiDelete,
};
