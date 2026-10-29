import React, { useEffect, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { MarkdownText } from "../../src/MarkdownText";
import { ScreenHeader } from "../../src/ScreenHeader";
import { colors } from "../../src/theme";
import { getGreeting } from "../../src/greeting";
import { openExternalUrl } from "../../src/openExternalUrl";
import { useAuth } from "../../src/auth";
import { clearChat, loadChat, recentWithinBudget, saveChat } from "../../src/chatStore";
import {
  BudgetPayload,
  ChatTurn,
  ComparePayload,
  CompareFormSpec,
  DosePayload,
  DoseFormSpec,
  FormSpec,
  RecommendedArticle,
  RecommendedProduct,
  sendChatMessageStream,
} from "../../src/api";
import BudgetCard from "../../src/BudgetCard";
import DoseCard from "../../src/DoseCard";
import CompareCard from "../../src/CompareCard";

interface Message {
  id: string;
  role: "user" | "bot";
  text: string;
  products?: RecommendedProduct[];
  article?: RecommendedArticle;
  form?: FormSpec;
  doseForm?: DoseFormSpec;
  compareForm?: CompareFormSpec;
  // The question this form was a reply to. Turn 2 resends it so history stays
  // coherent and the router still classifies the turn the same way.
  question?: string;
}

let nextId = 1;
/** The profile as a conversation turn, or nothing when there is no profile.
 *  A single user turn: two consecutive user messages are valid in the chat
 *  format, and inventing an assistant reply the assistant never gave would put
 *  words in its mouth. */
function profileTurns(
  profile: { name: string; province?: string; crops?: string } | null,
): ChatTurn[] {
  if (!profile?.name) return [];
  const parts = [`Adım ${profile.name}.`];
  if (profile.province) parts.push(`${profile.province}'dayım.`);
  if (profile.crops) parts.push(`${profile.crops} yetiştiriyorum.`);
  parts.push("Bunu aklında tut, her cevapta tekrar etme.");
  return [{ role: "user", content: parts.join(" ") }];
}

function newId() {
  return String(nextId++);
}

export default function ChatScreen() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [restored, setRestored] = useState(false);
  const { profile } = useAuth();
  const profileArea =
    profile?.area && profile.areaUnit
      ? { value: profile.area, unit: profile.areaUnit }
      : null;
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const historyRef = useRef<ChatTurn[]>([]);
  const scrollRef = useRef<ScrollView>(null);

  // Restore the stored conversation once. Until this finishes the screen shows
  // nothing rather than the greeting, so a returning user does not watch their
  // history be replaced a frame later.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const saved = await loadChat();
      if (cancelled) return;
      if (saved && saved.messages.length) {
        setMessages(saved.messages as Message[]);
        historyRef.current = saved.history;
        // Keep ids ahead of anything restored, or a new bubble can collide with
        // an old one and React will reuse the wrong row.
        const maxId = Math.max(0, ...saved.messages.map((m) => Number(m.id) || 0));
        nextId = maxId + 1;
      } else {
        setMessages([{ id: newId(), role: "bot", text: getGreeting() }]);
      }
      setRestored(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Persist after every change, but only once the restore has run - saving the
  // empty initial state would wipe the very history we are about to load.
  useEffect(() => {
    if (!restored) return;
    saveChat({
      messages: messages.map(({ form, doseForm, compareForm, ...rest }) => rest) as never,
      history: historyRef.current,
    });
  }, [messages, restored]);

  async function startNewChat() {
    await clearChat();
    historyRef.current = [];
    setMessages([{ id: newId(), role: "bot", text: getGreeting() }]);
  }

  function scrollToEnd() {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
  }

  function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { id: newId(), role: "user", text }]);
    sendTurn(text);
  }

  // The network half, shared by a typed message and a submitted budget form.
  // The caller owns the user bubble: a form turn shows the values entered, not
  // the question repeated.
  function sendTurn(text: string, budget?: BudgetPayload, dose?: DosePayload,
                    compare?: ComparePayload) {
    // Prior turns only - the current message is sent separately as `text`,
    // so it must not also be the last entry in the history we send.
    //
    // The profile is prepended as the FIRST user turn so the assistant knows who
    // it is talking to and where they are. Doing it here rather than server-side
    // is deliberate: `history` is already part of the request, so this needs no
    // backend change and works against the older deployment too.
    //
    // It is NOT pushed into historyRef and NOT rendered as a bubble - the user
    // never typed it, so showing it as something they said would be a lie. It is
    // rebuilt from the current profile on every send, so editing the profile
    // takes effect on the next message with no extra wiring.
    // The profile always goes; the rest is trimmed to what the model's context
    // window can actually hold (see src/chatStore.ts for the measurement).
    const requestHistory = [
      ...profileTurns(profile),
      ...recentWithinBudget(historyRef.current),
    ];
    setLoading(true);
    scrollToEnd();

    const botId = newId();
    let accumulated = "";
    let products: RecommendedProduct[] = [];
    let started = false;

    sendChatMessageStream(text, requestHistory, {
      onToken: (content) => {
        accumulated += content;
        if (!started) {
          started = true;
          setStreamingId(botId);
          setMessages((prev) => [
            ...prev,
            { id: botId, role: "bot", text: accumulated, products },
          ]);
        } else {
          setMessages((prev) =>
            prev.map((m) => (m.id === botId ? { ...m, text: accumulated } : m))
          );
        }
        scrollToEnd();
      },
      onProducts: (p) => {
        // Arrives before the bot message exists (it's the first SSE event),
        // so it can't be applied via setMessages yet - stash it here and
        // attach it when the message is created in onToken above.
        products = p;
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, products: p } : m))
        );
      },
      // `onForm` arrives after the first `onToken`, so the bot message already
      // exists.
      onForm: (form) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, form, question: text } : m))
        );
      },
      onDoseForm: (doseForm) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, doseForm, question: text } : m))
        );
      },
      onCompareForm: (compareForm) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, compareForm, question: text } : m))
        );
      },
      // Sent after the answer and its products, so the message exists.
      onArticle: (article) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, article } : m))
        );
      },
      onDone: () => {
        historyRef.current.push({ role: "user", content: text });
        historyRef.current.push({ role: "assistant", content: accumulated });
        setLoading(false);
        setStreamingId(null);
        scrollToEnd();
      },
      onError: () => {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "bot",
            text: "Bağlantı hatası. Lütfen API sunucusunun çalıştığından emin olun ve tekrar deneyin.",
          },
        ]);
        setLoading(false);
        setStreamingId(null);
        scrollToEnd();
      },
    }, budget, dose, compare);
  }

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <ScreenHeader title="Ekolojik Tarım Asistanı" />

      {/* Only offered once there is something to clear, so a fresh install is
          not invited to reset an empty conversation. */}
      {messages.length > 1 ? (
        <View style={styles.toolbar}>
          <Pressable onPress={startNewChat} hitSlop={8} style={styles.newChat}>
            <Ionicons name="create-outline" size={16} color={colors.green} />
            <Text style={styles.newChatText}>Yeni sohbet</Text>
          </Pressable>
        </View>
      ) : null}

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.messages}
          contentContainerStyle={styles.messagesContent}
        >
          {messages.map((m) => (
            <View key={m.id}>
              <View
                style={[
                  styles.bubble,
                  m.role === "user" ? styles.bubbleUser : styles.bubbleBot,
                ]}
              >
                {m.role === "user" ? (
                  <Text style={styles.userText}>{m.text}</Text>
                ) : (
                  <MarkdownText text={m.text} color={colors.dark} />
                )}
              </View>
              {m.products && m.products.length > 0 && (
                <View style={styles.products}>
                  {m.products.map((p, i) => (
                    <TouchableOpacity
                      key={i}
                      style={styles.productChip}
                      onPress={() => openExternalUrl(p.link)}
                    >
                      <View style={styles.dot} />
                      <Text style={styles.productText}>{p.title}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              {m.article && (
                // Opens inside the app, on the Akademi tab's own article
                // screen - the company's content stays in the company's app.
                <TouchableOpacity
                  style={styles.articleLink}
                  onPress={() =>
                    router.push({
                      pathname: "/article/[id]",
                      params: { id: encodeURIComponent(m.article!.link) },
                    })
                  }
                >
                  <Ionicons name="book-outline" size={16} color={colors.green} />
                  <View style={styles.articleBody}>
                    <Text style={styles.articleLabel}>Akademi'den ilgili yazı</Text>
                    <Text style={styles.articleTitle}>{m.article.title}</Text>
                  </View>
                </TouchableOpacity>
              )}
              {m.form && (
                <BudgetCard
                  form={m.form}
                  profileArea={profileArea}
                  disabled={loading}
                  onSubmit={(payload, summary) => {
                    if (loading) return;
                    setMessages((prev) => [
                      // The card is consumed: replace it, so a stale form cannot
                      // be submitted twice.
                      ...prev.map((x) =>
                        x.id === m.id ? { ...x, form: undefined } : x
                      ),
                      { id: newId(), role: "user", text: summary },
                    ]);
                    // `question` is written in the same setState as `form`, so
                    // it is always there; `summary` is the fallback only because
                    // /api/chat requires a non-empty message. Either is safe -
                    // turn 2 no longer depends on how the message routes.
                    sendTurn(m.question ?? summary, payload);
                  }}
                />
              )}
              {m.doseForm && (
                <DoseCard
                  form={m.doseForm}
                  profileArea={profileArea}
                  disabled={loading}
                  onSubmit={(payload, summary) => {
                    if (loading) return;
                    setMessages((prev) => [
                      // The card is consumed: replace it, so a stale card
                      // cannot be submitted twice.
                      ...prev.map((x) =>
                        x.id === m.id ? { ...x, doseForm: undefined } : x
                      ),
                      { id: newId(), role: "user", text: summary },
                    ]);
                    sendTurn(m.question ?? summary, undefined, payload);
                  }}
                />
              )}
              {m.compareForm && (
                <CompareCard
                  form={m.compareForm}
                  disabled={loading}
                  onSubmit={(payload, summary) => {
                    if (loading) return;
                    setMessages((prev) => [
                      ...prev.map((x) =>
                        x.id === m.id ? { ...x, compareForm: undefined } : x
                      ),
                      { id: newId(), role: "user", text: summary },
                    ]);
                    sendTurn(m.question ?? summary, undefined, undefined, payload);
                  }}
                />
              )}
            </View>
          ))}
          {loading && !streamingId && (
            <View style={[styles.bubble, styles.bubbleBot]}>
              <Text style={styles.typingText}>Yazıyor...</Text>
            </View>
          )}
        </ScrollView>

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Bitkileriniz hakkında bir soru sorun..."
            placeholderTextColor="#9aa393"
            onSubmitEditing={handleSend}
            returnKeyType="send"
            editable={!loading}
          />
          <TouchableOpacity
            style={[styles.sendButton, loading && styles.sendButtonDisabled]}
            onPress={handleSend}
            disabled={loading}
          >
            <Text style={styles.sendIcon}>&#10148;</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  toolbar: {
    flexDirection: "row",
    justifyContent: "flex-end",
    paddingHorizontal: 14,
    paddingTop: 8,
  },
  newChat: { flexDirection: "row", alignItems: "center", gap: 4 },
  newChatText: { color: colors.green, fontSize: 13, fontWeight: "600" },
  flex: { flex: 1 },
  container: { flex: 1, backgroundColor: colors.bg },
  messages: { flex: 1 },
  messagesContent: { padding: 14, gap: 10 },
  bubble: {
    maxWidth: "84%",
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderRadius: 14,
    marginBottom: 10,
  },
  bubbleUser: {
    alignSelf: "flex-end",
    backgroundColor: colors.green,
    borderBottomRightRadius: 4,
  },
  bubbleBot: {
    alignSelf: "flex-start",
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
    borderBottomLeftRadius: 4,
  },
  userText: { color: "#fff", fontSize: 13.5, lineHeight: 19 },
  typingText: { color: colors.muted, fontStyle: "italic", fontSize: 13.5 },
  products: { alignSelf: "flex-start", maxWidth: "88%", gap: 6, marginBottom: 10 },
  productChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.greenLight,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    marginBottom: 6,
  },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.green },
  productText: { color: colors.dark, fontSize: 12.5, flexShrink: 1 },
  articleLink: {
    alignSelf: "flex-start",
    maxWidth: "88%",
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.greenLight,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    marginBottom: 10,
  },
  articleBody: { flexShrink: 1 },
  articleLabel: { color: colors.muted, fontSize: 11 },
  articleTitle: { color: colors.dark, fontSize: 12.5, fontWeight: "600" },
  inputRow: {
    flexDirection: "row",
    gap: 8,
    padding: 10,
    borderTopWidth: 1,
    borderTopColor: "#e6e6e6",
    backgroundColor: colors.white,
    alignItems: "center",
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.inputBorder,
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 13.5,
    color: colors.dark,
  },
  sendButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.green,
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonDisabled: { opacity: 0.5 },
  sendIcon: { color: "#fff", fontSize: 15 },
});
