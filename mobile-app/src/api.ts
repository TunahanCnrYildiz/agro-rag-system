// Chat API client. Uses the unified (non-streaming) JSON response mode —
// React Native's fetch does not reliably support reading a streaming
// response body (no ReadableStream support), unlike the browser widget.
//
// Platform note: 127.0.0.1 only reaches the API when the app runs in the
// same browser/host as the server (e.g. `expo start --web`). An Android
// emulator needs 10.0.2.2, and a physical device needs the host machine's
// LAN IP — change API_BASE accordingly when testing on-device.
export const API_BASE = "http://127.0.0.1:8000";

export type ChatRole = "user" | "assistant";

export interface ChatTurn {
  role: ChatRole;
  content: string;
}

export interface RecommendedProduct {
  title: string;
  link: string;
}

export interface ChatResponse {
  answer: string;
  recommended_products: RecommendedProduct[];
}

export async function sendChatMessage(
  message: string,
  history: ChatTurn[]
): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, stream: false }),
  });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}
