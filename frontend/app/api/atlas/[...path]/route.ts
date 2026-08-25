import { NextRequest, NextResponse } from "next/server";

import { serverConfig } from "@/lib/config";

/**
 * Narrow proxy to the Atlas backend for the Developer View and demo controls.
 *
 * Two reasons this exists rather than the browser calling the backend directly:
 *
 * 1. The backend's shared secret stays server-side.
 * 2. The allow-list below means this proxy can only reach the demo/observability
 *    endpoints. It cannot be used to reach the business API -- in particular it
 *    cannot modify an order. The only path to a write is through the agent's
 *    own authenticated tool call.
 */
const ALLOWED = new Set(["demo/activity", "demo/audit", "demo/reset", "demo/fault"]);

async function forward(request: NextRequest, path: string[], method: string) {
  const joined = path.join("/");
  if (!ALLOWED.has(joined)) {
    return NextResponse.json(
      { error: { code: "NOT_PROXYABLE", message: `Path /${joined} is not proxyable.` } },
      { status: 404 },
    );
  }

  const target = new URL(`${serverConfig.atlasBaseUrl.replace(/\/$/, "")}/api/${joined}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (serverConfig.atlasApiKey) headers["X-Atlas-Api-Key"] = serverConfig.atlasApiKey;

  try {
    const response = await fetch(target, {
      method,
      headers,
      body: method === "GET" || method === "DELETE" ? undefined : await request.text(),
      cache: "no-store",
    });
    const text = await response.text();
    return new NextResponse(text || "{}", {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "BACKEND_UNREACHABLE",
          message: `Could not reach the Atlas backend at ${serverConfig.atlasBaseUrl}. Is it running?`,
        },
      },
      { status: 503 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  return forward(request, (await ctx.params).path, "GET");
}

export async function POST(request: NextRequest, ctx: Ctx) {
  return forward(request, (await ctx.params).path, "POST");
}

export async function DELETE(request: NextRequest, ctx: Ctx) {
  return forward(request, (await ctx.params).path, "DELETE");
}
