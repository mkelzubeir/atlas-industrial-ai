import { NextResponse } from "next/server";

import { assertAgentId, serverConfig } from "@/lib/config";

/**
 * Mints a short-lived conversation token for the browser.
 *
 * The ElevenLabs API key stays on the server. The browser gets a token scoped
 * to a single conversation, which is the difference between "this page can
 * start a call with our agent" and "this page can do anything our account can".
 */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const agentId = assertAgentId();

    // No API key configured: the agent must be public, so the client can
    // connect with the agent id alone. Useful for a first run-through.
    if (!serverConfig.elevenLabsApiKey) {
      return NextResponse.json({ agentId, token: null, mode: "public" });
    }

    const url = new URL("https://api.elevenlabs.io/v1/convai/conversation/token");
    url.searchParams.set("agent_id", agentId);

    const response = await fetch(url, {
      headers: { "xi-api-key": serverConfig.elevenLabsApiKey },
      cache: "no-store",
    });

    if (!response.ok) {
      const detail = await response.text();
      console.error("[atlas] conversation token request failed", response.status, detail);
      return NextResponse.json(
        {
          error:
            "Could not start a session with ElevenLabs. Check ELEVENLABS_API_KEY and the agent id.",
        },
        { status: 502 },
      );
    }

    const body = (await response.json()) as { token?: string };
    if (!body.token) {
      return NextResponse.json(
        { error: "ElevenLabs did not return a conversation token." },
        { status: 502 },
      );
    }

    return NextResponse.json({ agentId, token: body.token, mode: "token" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error.";
    console.error("[atlas] conversation token error", error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
