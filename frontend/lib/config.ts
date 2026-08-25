/**
 * Server-side configuration.
 *
 * Everything secret is read here, in server-only modules. The browser never
 * sees the ElevenLabs key or the Atlas shared secret -- it talks to this app's
 * own route handlers, which hold the credentials and forward the call.
 *
 * The only value that reaches the client is the agent id, which is not a
 * secret: it identifies a public agent, and the conversation token that
 * actually authorises a session is minted per call.
 */

export const serverConfig = {
  elevenLabsApiKey: process.env.ELEVENLABS_API_KEY ?? "",
  agentId: process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID ?? "",
  atlasBaseUrl: process.env.ATLAS_BACKEND_URL ?? "http://127.0.0.1:8000",
  atlasApiKey: process.env.ATLAS_API_KEY ?? "",
};

export function assertAgentId(): string {
  if (!serverConfig.agentId) {
    throw new Error(
      "NEXT_PUBLIC_ELEVENLABS_AGENT_ID is not set. Run scripts/provision_agent.py and " +
        "copy the agent id it prints into frontend/.env.local.",
    );
  }
  return serverConfig.agentId;
}
