// Chat API client. Uses the unified (non-streaming) JSON response mode —
// React Native's fetch does not reliably support reading a streaming
// response body (no ReadableStream support), unlike the browser widget.
//
// Platform note: a physical device can't reach 127.0.0.1 (that's the phone
// itself) - it needs the host machine's LAN IP instead, and both devices must
// be on the same Wi-Fi. This IP is assigned by the router (DHCP) and can
// change; if the app can't reach the API, check the PC's current IP
// (ipconfig / Settings > Network) and update it here.
// Android emulator (not a physical device) would instead use 10.0.2.2.
export const API_BASE = "http://192.168.1.103:8000";

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
