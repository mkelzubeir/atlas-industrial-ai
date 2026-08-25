import { ConsoleShell } from "@/components/ConsoleShell";
import { serverConfig } from "@/lib/config";

export default function Home() {
  // The agent id is not a secret; the per-call conversation token is minted
  // server-side by /api/conversation-token.
  return <ConsoleShell agentId={serverConfig.agentId} />;
}
