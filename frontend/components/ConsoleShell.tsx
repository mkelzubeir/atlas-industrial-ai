"use client";

import { ConversationProvider } from "@elevenlabs/react";

import { AtlasConsole } from "./AtlasConsole";

/**
 * `useConversation` must run inside a `ConversationProvider`, so the shell
 * exists purely to establish that boundary.
 */
export function ConsoleShell({ agentId }: { agentId: string }) {
  return (
    <ConversationProvider>
      <AtlasConsole agentId={agentId} />
    </ConversationProvider>
  );
}
