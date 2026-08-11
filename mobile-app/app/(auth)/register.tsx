import React, { useState } from "react";
import { Pressable, Text } from "react-native";
import { router } from "expo-router";
import { AuthScreen, Field, authStyles } from "../../src/AuthForm";
import { useAuth } from "../../src/auth";

export default function RegisterScreen() {
  const { signUp } = useAuth();
  const [name, setName] = useState("");
  const [province, setProvince] = useState("");
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
      await signUp({ name, province });
      router.replace("/(tabs)");
    } catch {
      setError("Profil kaydedilemedi. Lütfen tekrar deneyin.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthScreen
      title="Profil oluştur"
      subtitle="Size daha iyi yardımcı olabilmemiz için birkaç bilgi."
      error={error}
      submitLabel={busy ? "Kaydediliyor..." : "Profili oluştur"}
      onSubmit={submit}
      disabled={busy}
      footer={
        <Pressable onPress={() => router.replace("/(auth)/login")}>
          <Text style={[authStyles.hint, { textAlign: "center", marginTop: 16 }]}>
            Zaten profiliniz var mı? Giriş yapın
          </Text>
        </Pressable>
      }
    >
      <Field
        label="Ad Soyad"
        placeholder="Örn. Ahmet Yılmaz"
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
        returnKeyType="next"
      />
      <Field
        label="İl (isteğe bağlı)"
        placeholder="Örn. Manisa"
        hint="Bölgenize uygun öneriler için kullanılır. Sonradan da ekleyebilirsiniz."
        value={province}
        onChangeText={setProvince}
        autoCapitalize="words"
        returnKeyType="done"
        onSubmitEditing={submit}
      />
    </AuthScreen>
  );
}
