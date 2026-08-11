import React, { useState } from "react";
import { Pressable, Text } from "react-native";
import { router } from "expo-router";
import { AuthScreen, Field, authStyles } from "../../src/AuthForm";
import { useAuth } from "../../src/auth";

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!name.trim()) {
      setError("Adınızı yazın.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const ok = await signIn(name);
      if (ok) {
        router.replace("/(tabs)");
      } else {
        setError("Bu cihazda bu isimle bir profil bulunamadı.");
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
        <Pressable onPress={() => router.replace("/(auth)/register")}>
          <Text style={[authStyles.hint, { textAlign: "center", marginTop: 16 }]}>
            Profiliniz yok mu? Yeni profil oluşturun
          </Text>
        </Pressable>
      }
    >
      <Field
        label="Ad Soyad"
        placeholder="Profil oluştururken yazdığınız ad"
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
        returnKeyType="done"
        onSubmitEditing={submit}
      />
    </AuthScreen>
  );
}
