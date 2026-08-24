export type Speaker = "rep" | "distributor" | "unknown";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error";

export interface Turn {
  id: string;
  speaker: Speaker;
  /** Diarization label from Deepgram (speaker 0 / 1), before roles are known. */
  speakerTag: number | null;
  text: string;
  isFinal: boolean;
  confidence: number | null;
  ts: number;
}

export interface FlashCard {
  id: string;
  content: string;
  triggerReason: string;
  category: string | null;
  latencyMs: number | null;
  toolsUsed: string[];
  inputTokens: number | null;
  outputTokens: number | null;
  ts: number;
}

export interface Distributor {
  id: string;
  name: string;
  region: string;
  aum_tier: string;
  risk_appetite: string;
}

/** A diarized voice the rep can identify as themselves. */
export interface SpeakerOption {
  tag: number;
  sample: string;
}

/** Messages the backend pushes over the conversation socket. */
export type ServerEvent =
  | {
      type: "ready";
      conversation_id: string;
      transcribing: boolean;
      agent_enabled: boolean;
    }
  | {
      type: "transcript";
      id: string;
      speaker: Speaker;
      speaker_tag: number | null;
      text: string;
      is_final: boolean;
      confidence: number | null;
      start: number;
      end: number;
    }
  | { type: "role_prompt"; speakers: SpeakerOption[] }
  | { type: "roles_assigned"; roles: Record<string, Speaker> }
  | {
      type: "flash_card";
      id: string;
      content: string;
      trigger_reason: string;
      category: string | null;
      latency_ms: number | null;
      tools_used: string[];
      input_tokens: number;
      output_tokens: number;
    }
  | {
      type: "trigger";
      triggered: boolean;
      reason: string;
      confidence: number;
    }
  | { type: "card_skipped"; reason: string; latency_ms: number }
  | { type: "stats"; bytes_received: number; chunks_received: number }
  | { type: "error"; message: string };

/** Messages the client sends back over the same socket. */
export type ClientControl = { type: "assign_role"; rep_tag: number };
