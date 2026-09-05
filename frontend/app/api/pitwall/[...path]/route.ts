import { NextRequest, NextResponse } from "next/server";

const backend = process.env.PITWALL_API_URL ?? "http://127.0.0.1:8000";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  try {
    if (path[0] !== "api" || path[1] !== "v1" || path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part))) {
      return NextResponse.json({ detail: "Unknown API route" }, { status: 404 });
    }
    const target = new URL(path.join("/"), `${backend.replace(/\/$/, "")}/`);
    target.search = request.nextUrl.search;
    const body = request.method === "GET" ? undefined : await request.text();
    const upstream = await fetch(target, {
      method: request.method,
      body,
      headers: {
        accept: "application/json",
        ...(body ? { "content-type": request.headers.get("content-type") ?? "application/json" } : {}),
      },
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(20_000)]),
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
        ...(upstream.headers.get("x-request-id")
          ? { "x-request-id": upstream.headers.get("x-request-id")! }
          : {}),
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Pit-wall API is unavailable. Start it with `pitwall serve`." },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
