/**
 * Shared shell for the sign-in and sign-up screens.
 *
 * Both screens are the same layout with different fields and copy, so they
 * share one component rather than being copy-pasted — the two would drift
 * otherwise, and the drift would be visible to the user.
 */
import React from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "./theme";

export function Field({
  label,
  hint,
  ...props
}: { label: string; hint?: string } & React.ComponentProps<typeof TextInput>) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={styles.input}
        placeholderTextColor={colors.muted}
        autoCorrect={false}
        {...props}
      />
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

export function AuthScreen({
  title,
  subtitle,
  children,
  error,
  submitLabel,
  onSubmit,
  disabled,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  error?: string | null;
  submitLabel: string;
  onSubmit: () => void;
  disabled?: boolean;
  footer: React.ReactNode;
}) {
  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.brand}>Ekolojik Tarım Asistanı</Text>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>

          {children}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Pressable
            style={({ pressed }) => [
              styles.button,
              (disabled || pressed) && styles.buttonMuted,
            ]}
            onPress={onSubmit}
            disabled={disabled}
          >
            <Text style={styles.buttonText}>{submitLabel}</Text>
          </Pressable>

          {footer}

          {/* Said plainly, on the screen itself, because a login box that looks
              real implies a server behind it. There is not one. */}
          <Text style={styles.notice}>
            Bilgileriniz yalnızca bu cihazda saklanır, sunucuya gönderilmez.
            Parola istenmez.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: { padding: 24, paddingTop: 48, gap: 4 },
  brand: { color: colors.green, fontSize: 14, fontWeight: "700", marginBottom: 24 },
  title: { color: colors.dark, fontSize: 26, fontWeight: "700" },
  subtitle: { color: colors.muted, fontSize: 14, lineHeight: 20, marginBottom: 20 },
  field: { marginBottom: 14 },
  label: { color: colors.dark, fontSize: 13, fontWeight: "600", marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.inputBorder,
    backgroundColor: colors.white,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: colors.dark,
  },
  hint: { color: colors.muted, fontSize: 12, marginTop: 5 },
  error: { color: "#b3261e", fontSize: 13, marginBottom: 10 },
  button: {
    backgroundColor: colors.green,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 6,
  },
  buttonMuted: { opacity: 0.7 },
  buttonText: { color: colors.white, fontSize: 15, fontWeight: "700" },
  notice: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17,
    marginTop: 28,
    textAlign: "center",
  },
});

export const authStyles = styles;
