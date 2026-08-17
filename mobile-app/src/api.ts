// Chat API client. Uses the unified (non-streaming) JSON response mode —
// React Native's fetch does not reliably support reading a streaming
// response body (no ReadableStream support), unlike the browser widget.
//
// Backend base URL. Override at build time with the EXPO_PUBLIC_API_BASE env var
// (e.g. in mobile-app/.env or the shell) so pointing at a hosted backend needs
// no code edit; the LAN IP below is only the local-dev default.
//
// Platform note: a physical device can't reach 127.0.0.1 (that's the phone
// itself) - it needs the host machine's LAN IP instead, and both devices must
// be on the same Wi-Fi. This IP is assigned by the router (DHCP) and can
// change; if the app can't reach the API, check the PC's current IP
// (ipconfig / Settings > Network) and set EXPO_PUBLIC_API_BASE (or edit below).
// Android emulator (not a physical device) would instead use 10.0.2.2.
export const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE ?? "http://192.168.1.102:8000";

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

export interface BudgetFieldValue {
  value: string;
  unit: string;
}

export interface BudgetPayload {
  area?: BudgetFieldValue;
  yield_total?: BudgetFieldValue;
  price?: BudgetFieldValue;
  cost?: BudgetFieldValue;
  crop?: string | null;
}

export interface FormUnit {
  id: string;
  label: string;
}

export interface FormField {
  id: string;
  label: string;
  required: boolean;
  units: FormUnit[];
  // Empty in P1; P2 fills these from the norm layer without a wire change.
  value: string;
  source: "user" | "norm" | "empty";
  error: string | null;
}

export interface FormSpec {
  fields: FormField[];
}

export interface ChatStreamHandlers {
  onToken: (content: string) => void;
  onProducts: (products: RecommendedProduct[]) => void;
  onForm?: (form: FormSpec) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}

// Uses XMLHttpRequest + onprogress instead of fetch's ReadableStream body,
// which React Native does not deliver incrementally.
export function sendChatMessageStream(
  message: string,
  history: ChatTurn[],
  handlers: ChatStreamHandlers,
  budget?: BudgetPayload
): void {
  const xhr = new XMLHttpRequest();
  let processedEvents = 0;

  function processUpTo(text: string) {
    const parts = text.split("\n\n");
    const complete = parts.slice(0, -1);
    for (let i = processedEvents; i < complete.length; i++) {
      const line = complete[i];
      if (!line.startsWith("data: ")) continue;
      let evt: any;
      try {
        evt = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (evt.type === "products") {
        handlers.onProducts(evt.recommended_products);
      } else if (evt.type === "token") {
        handlers.onToken(evt.content);
      } else if (evt.type === "form") {
        handlers.onForm?.(evt.form);
      }
    }
    processedEvents = complete.length;
  }

  xhr.open("POST", `${API_BASE}/api/chat`);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.onprogress = () => processUpTo(xhr.responseText);
  xhr.onload = () => {
    processUpTo(xhr.responseText);
    if (xhr.status >= 200 && xhr.status < 300) {
      handlers.onDone();
    } else {
      handlers.onError(new Error(`API error: ${xhr.status}`));
    }
  };
  xhr.onerror = () => handlers.onError(new Error("Network error"));
  xhr.send(JSON.stringify({ message, history, stream: true, budget }));
}

export interface CatalogProduct {
  product_name: string;
  description: string;
  category: string;
  source_url: string;
  image_url: string;
}

export interface Article {
  title: string;
  excerpt: string;
  category: string;
  date: string;
  source_url: string;
  image_url: string;
  content: string;
}

export async function fetchProducts(): Promise<CatalogProduct[]> {
  const resp = await fetch(`${API_BASE}/api/products`);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

export async function fetchArticles(): Promise<Article[]> {
  const resp = await fetch(`${API_BASE}/api/articles`);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}
