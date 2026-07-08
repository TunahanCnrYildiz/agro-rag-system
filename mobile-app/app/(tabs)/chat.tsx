import React, { useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { MarkdownText } from "../../src/MarkdownText";
import { ScreenHeader } from "../../src/ScreenHeader";
import { colors } from "../../src/theme";
import { getGreeting } from "../../src/greeting";
import { openExternalUrl } from "../../src/openExternalUrl";
import {
  ChatTurn,
  RecommendedProduct,
  sendChatMessage,
} from "../../src/api";

interface Message {
  id: string;
  role: "user" | "bot";
  text: string;
  products?: RecommendedProduct[];
}

let nextId = 1;
function newId() {
  return String(nextId++);
}

export default function ChatScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: newId(),
      role: "bot",
      text: getGreeting(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const historyRef = useRef<ChatTurn[]>([]);
  const scrollRef = useRef<ScrollView>(null);

  function scrollToEnd() {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { id: newId(), role: "user", text }]);
    // Prior turns only - the current message is sent separately as `text`,
    // so it must not also be the last entry in the history we send.
    const requestHistory = historyRef.current.slice();
    setLoading(true);
    scrollToEnd();

    try {
      const resp = await sendChatMessage(text, requestHistory);
      historyRef.current.push({ role: "user", content: text });
      historyRef.current.push({ role: "assistant", content: resp.answer });
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "bot",
          text: resp.answer,
          products: resp.recommended_products,
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "bot",
          text: "Bağlantı hatası. Lütfen API sunucusunun çalıştığından emin olun ve tekrar deneyin.",
        },
      ]);
    } finally {
      setLoading(false);
      scrollToEnd();
    }
  }

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <ScreenHeader title="Ekolojik Tarım Asistanı" />

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
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
            </View>
          ))}
          {loading && (
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
