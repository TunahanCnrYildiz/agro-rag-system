import React, { useState } from "react";
import { Pressable, Text } from "react-native";
import { router } from "expo-router";
import { AuthScreen, Field, authStyles } from "../../src/AuthForm";
import { useAuth } from "../../src/auth";

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!userId.trim() || !password) {
      setError("Kullanıcı ID ve şifrenizi girin.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const ok = await signIn(userId, password);
      if (ok) {
        router.replace("/(tabs)");
      } else {
        // One message for both a wrong ID and a wrong password, so the screen
        // does not confirm which IDs exist on the device.
        setError("Kullanıcı ID veya şifre hatalı.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthScreen
      title="Giriş yap"
      subtitle="Bu cihazda kayıtlı profilinizle devam edin."
      error={error}
      submitLabel={busy ? "Kontrol ediliyor..." : "Giriş yap"}
      onSubmit={submit}
      disabled={busy}
      footer={
        <>
          <Pressable onPress={() => router.push("/(auth)/forgot")}>
            <Text style={[authStyles.hint, { textAlign: "center", marginTop: 14 }]}>
              Şifremi unuttum
            </Text>
          </Pressable>
        <Pressable onPress={() => router.replace("/(auth)/register")}>
          <Text style={[authStyles.hint, { textAlign: "center", marginTop: 16 }]}>
            Profiliniz yok mu? Yeni profil oluşturun
          </Text>
        </Pressable>
        </>
      }
    >
      <Field
        label="Kullanıcı ID"
        placeholder="Profil oluştururken belirlediğiniz ID"
        value={userId}
        onChangeText={setUserId}
        autoCapitalize="none"
      />
      <Field
        label="Şifre"
        placeholder="Şifreniz"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoCapitalize="none"
        onSubmitEditing={submit}
      />
    </AuthScreen>
  );
}
