const API_ROOT = "/api/pitwall/api/v1";

function detailFrom(value: unknown): string | null {
  if (!value || typeof value !== "object" || !("detail" in value)) return null;
  if (typeof value.detail === "string") return value.detail;
  if (Array.isArray(value.detail)) {
    return value.detail.map((item: { msg?: string }) => item.msg ?? "Invalid value").join("; ");
  }
  return null;
}

export async function pitwallRequest<T>(
  path: string,
  init?: RequestInit,
  signal?: AbortSignal,
): Promise<T> {
  const timeout = AbortSignal.timeout(25_000);
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(detailFrom(payload) ?? `Pit-wall request failed (${response.status})`);
  }
  if (payload === null) throw new Error("The API returned an invalid response. Please retry.");
  return payload as T;
}
