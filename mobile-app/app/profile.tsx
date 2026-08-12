/**
 * Profile screen.
 *
 * Editing the details and changing the password BOTH genuinely work — they are
 * local operations and need no server, so they were built rather than mocked.
 * Password recovery works too (see app/(auth)/forgot.tsx); what is missing is
 * only its DELIVERY channel, since there is no server to send mail from. What is
 * genuinely absent is syncing between devices, and the screen says so rather
 * than pretending, because a control that looks live and does nothing is worse
 * than one that explains itself.
 */
import React, { useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Field } from "../src/AuthForm";
import { ScreenHeader } from "../src/ScreenHeader";
import { colors } from "../src/theme";
import { forgetProfile, useAuth } from "../src/auth";

export default function ProfileScreen() {
  const { profile, updateProfile, changePassword, signOut } = useAuth();

  const [name, setName] = useState(profile?.name ?? "");
  const [email, setEmail] = useState(profile?.email ?? "");
  const [province, setProvince] = useState(profile?.province ?? "");
  const [crops, setCrops] = useState(profile?.crops ?? "");
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [next2, setNext2] = useState("");
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [pwError, setPwError] = useState<string | null>(null);

  if (!profile) return null;

  async function saveDetails() {
    if (!name.trim()) return setDetailError("Adınızı ve soyadınızı yazın.");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
      return setDetailError("Geçerli bir e-posta adresi yazın.");
    setDetailError(null);
    await updateProfile({ name, email, province, crops });
    setSavedMsg("Bilgileriniz kaydedildi.");
    setTimeout(() => setSavedMsg(null), 2500);
  }

  async function savePassword() {
    if (!current || !next) return setPwError("Tüm alanları doldurun.");
    if (next.length < 4) return setPwError("Yeni şifre en az 4 karakter olmalı.");
    if (next !== next2) return setPwError("Yeni şifreler birbirini tutmuyor.");
    setPwError(null);
    const ok = await changePassword(current, next);
    if (!ok) {
      setPwError("Mevcut şifreniz hatalı.");
      return;
    }
    setCurrent("");
    setNext("");
    setNext2("");
    setPwMsg("Şifreniz değiştirildi.");
    setTimeout(() => setPwMsg(null), 2500);
  }

  function confirmDelete() {
    Alert.alert(
      "Profili sil",
      "Bu cihazdaki profil bilgileriniz silinecek. Devam edilsin mi?",
      [
        { text: "Vazgeç", style: "cancel" },
        {
          text: "Sil",
          style: "destructive",
          onPress: async () => {
            await forgetProfile();
            await signOut();
            router.replace("/(auth)/register");
          },
        },
      ],
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScreenHeader title="Profilim" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={styles.idRow}>
            <Ionicons name="person-circle-outline" size={44} color={colors.green} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.idName} numberOfLines={1}>{profile.name}</Text>
              <Text style={styles.idSub}>Kullanıcı ID: {profile.userId}</Text>
            </View>
          </View>

          <Text style={styles.section}>Bilgilerim</Text>
          <Field label="Ad Soyad" value={name} onChangeText={setName} autoCapitalize="words" />
          <Field
            label="E-posta"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
          />
          <Field
            label="İl"
            placeholder="Örn. Manisa"
            value={province}
            onChangeText={setProvince}
            autoCapitalize="words"
          />
          <Field
            label="Yetiştirdiğiniz ürünler"
            placeholder="Örn. domates, biber"
            value={crops}
            onChangeText={setCrops}
            autoCapitalize="none"
          />
          {detailError ? <Text style={styles.error}>{detailError}</Text> : null}
          {savedMsg ? <Text style={styles.ok}>{savedMsg}</Text> : null}
          <Pressable style={styles.button} onPress={saveDetails}>
            <Text style={styles.buttonText}>Bilgileri kaydet</Text>
          </Pressable>

          <Text style={styles.section}>Şifre değiştir</Text>
          <Field
            label="Mevcut şifre"
            value={current}
            onChangeText={setCurrent}
            secureTextEntry
            autoCapitalize="none"
          />
          <Field
            label="Yeni şifre"
            value={next}
            onChangeText={setNext}
            secureTextEntry
            autoCapitalize="none"
          />
          <Field
            label="Yeni şifre (tekrar)"
            value={next2}
            onChangeText={setNext2}
            secureTextEntry
            autoCapitalize="none"
          />
          {pwError ? <Text style={styles.error}>{pwError}</Text> : null}
          {pwMsg ? <Text style={styles.ok}>{pwMsg}</Text> : null}
          <Pressable style={styles.button} onPress={savePassword}>
            <Text style={styles.buttonText}>Şifreyi değiştir</Text>
          </Pressable>

          <Text style={styles.section}>Hesap</Text>
          <Pressable
            style={styles.rowButton}
            onPress={async () => {
              await signOut();
              router.replace("/(auth)/login");
            }}
          >
            <Ionicons name="log-out-outline" size={20} color={colors.dark} />
            <Text style={styles.rowText}>Çıkış yap</Text>
          </Pressable>
          <Pressable style={styles.rowButton} onPress={confirmDelete}>
            <Ionicons name="trash-outline" size={20} color="#b3261e" />
            <Text style={[styles.rowText, { color: "#b3261e" }]}>Profili sil</Text>
          </Pressable>

          <Text style={styles.notice}>
            Profiliniz yalnızca bu cihazda saklanır. Şifreniz şifrelenmiş olarak
            tutulur ve sunucuya gönderilmez. Şifre sıfırlama çalışır; yeni şifre
            e-posta gönderimi henüz aktif olmadığı için ekranda gösterilir.
            Cihazlar arası eşitleme henüz yoktur.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: { padding: 20, paddingBottom: 40 },
  idRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
  },
  idName: { color: colors.dark, fontSize: 17, fontWeight: "700" },
  idSub: { color: colors.muted, fontSize: 12, marginTop: 3 },
  section: {
    color: colors.dark,
    fontSize: 15,
    fontWeight: "700",
    marginTop: 22,
    marginBottom: 10,
  },
  error: { color: "#b3261e", fontSize: 13, marginBottom: 8 },
  ok: { color: colors.green, fontSize: 13, marginBottom: 8, fontWeight: "600" },
  button: {
    backgroundColor: colors.green,
    borderRadius: 10,
    paddingVertical: 13,
    alignItems: "center",
    marginTop: 4,
  },
  buttonText: { color: colors.white, fontSize: 15, fontWeight: "700" },
  rowButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 14,
    marginBottom: 8,
  },
  rowText: { color: colors.dark, fontSize: 15, fontWeight: "600" },
  notice: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17,
    marginTop: 22,
    textAlign: "center",
  },
});
