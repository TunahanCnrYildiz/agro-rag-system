/**
 * Conversation persistence.
 *
 * TWO DIFFERENT BUDGETS, and conflating them is the mistake this file exists to
 * avoid:
 *
 *   STORAGE is cheap. A typical exchange in this app is ~1 KB (measured: answers
 *   average ~900 characters), so 200 exchanges is ~200 KB against AsyncStorage's
 *   6 MB. The user can scroll back through all of it.
 *
 *   THE MODEL'S CONTEXT IS NOT. Measured 2026-08-12 against the real pipeline:
 *   the system prompt with retrieved corpus context is ~11,100 characters
 *   (~4,450 tokens) and generation reserves 2,048, leaving roughly 1,690 tokens
 *   — about 4,200 characters — of an 8,192-token window for history. So only the
 *   most recent few exchanges can actually be sent.
 *
 * Hence: keep everything the user might want to read, send only what fits.
 * Sending is budgeted by CHARACTERS rather than a fixed turn count, because four
 * long answers and twelve short ones occupy the same space.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { ChatTurn } from "./api";

const STORAGE_KEY = "eta.chat.v1";

/** One rendered bubble. Deliberately structural rather than importing the
 *  screen's own Message type: the bubbles carry things the model never sees
 *  (product cards, the greeting), and this module should not depend on the
 *  screen. Anything JSON-serialisable round-trips. */
export type StoredMessage = {
  id: string;
  role: "user" | "bot";
  text: string;
  products?: { title: string; link: string }[];
};

export type StoredChat = {
  messages: StoredMessage[];
  history: ChatTurn[];
};

/** Roughly 200 exchanges. Not a storage concern at ~1 KB each; it is here so the
 *  app cannot grow without bound over years of use. */
const MAX_TURNS = 400; // 200 exchanges = 400 turns

/** Characters of history sent to the model. Deliberately below the ~4,200 the
 *  measurement allows, because the corpus context varies in size and overflowing
 *  the window costs the whole answer, not just the oldest turn. */
export const SEND_BUDGET_CHARS = 3000;

export async function loadChat(): Promise<StoredChat | null> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (Array.isArray(p?.messages) && Array.isArray(p?.history)) {
      return { messages: p.messages, history: p.history };
    }
  } catch {
    // A corrupt value must start a fresh conversation, never crash the screen.
  }
  return null;
}

export async function saveChat(chat: StoredChat): Promise<void> {
  try {
    await AsyncStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        messages: chat.messages.slice(-MAX_TURNS),
        history: chat.history.slice(-MAX_TURNS),
      }),
    );
  } catch {
    // Losing the save is survivable; losing the screen is not.
  }
}

export async function clearChat(): Promise<void> {
  try {
    await AsyncStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * The most recent turns that fit in `budget` characters, oldest-first.
 *
 * Walks backwards and stops at the first turn that would overflow rather than
 * skipping it and continuing: dropping a turn from the middle would hand the
 * model a conversation that jumps, which reads worse than a shorter one.
 */
export function recentWithinBudget(
  history: ChatTurn[],
  budget: number = SEND_BUDGET_CHARS,
): ChatTurn[] {
  const out: ChatTurn[] = [];
  let used = 0;
  for (let i = history.length - 1; i >= 0; i--) {
    const cost = history[i].content.length;
    if (used + cost > budget) break;
    used += cost;
    out.unshift(history[i]);
  }
  return out;
}
