const API_ROOT = "/api/pitwall/api/v1";

function detailFrom(value: unknown): string | null {
  if (!value || typeof value !== "object" || !("detail" in value)) return null;
  return typeof value.detail === "string" ? value.detail : null;
}

export async function pitwallRequest<T>(
  path: string,
  init?: RequestInit,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, { ...init, signal });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(detailFrom(payload) ?? `Pit-wall request failed (${response.status})`);
  }
  return payload as T;
}
