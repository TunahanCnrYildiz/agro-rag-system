import React, { useState } from "react";
import { Pressable, Text } from "react-native";
import { router } from "expo-router";
import { AuthScreen, Field, authStyles } from "../../src/AuthForm";
import { useAuth } from "../../src/auth";

export default function RegisterScreen() {
  const { signUp } = useAuth();
  const [name, setName] = useState("");
  const [userId, setUserId] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [province, setProvince] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!name.trim()) return setError("Adınızı ve soyadınızı yazın.");
    if (userId.trim().length < 3) return setError("Kullanıcı ID en az 3 karakter olmalı.");
    // Pragmatic check, not a full RFC 5322 parser: the point is to catch a typo,
    // not to reject an unusual but valid address.
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
      return setError("Geçerli bir e-posta adresi yazın.");
    if (password.length < 4) return setError("Şifre en az 4 karakter olmalı.");
    if (password !== password2) return setError("Şifreler birbirini tutmuyor.");

    setError(null);
    setBusy(true);
    try {
      await signUp({ name, userId, email, password, province });
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
      />
      <Field
        label="Kullanıcı ID"
        placeholder="Örn. ahmety"
        hint="Girişte bu ID'yi kullanacaksınız."
        value={userId}
        onChangeText={setUserId}
        autoCapitalize="none"
      />
      <Field
        label="E-posta"
        placeholder="ornek@eposta.com"
        hint="Şifrenizi unutursanız hesabınıza erişmek için kullanılacak."
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
      />
      <Field
        label="Şifre"
        placeholder="En az 4 karakter"
        // Said on the screen, not just in a code comment: people reuse passwords,
        // and this one is protected by a device, not by a service.
        hint="Başka yerlerde kullandığınız bir şifreyi buraya yazmayın."
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoCapitalize="none"
      />
      <Field
        label="Şifre (tekrar)"
        placeholder="Şifreyi tekrar yazın"
        value={password2}
        onChangeText={setPassword2}
        secureTextEntry
        autoCapitalize="none"
      />
      <Field
        label="İl (isteğe bağlı)"
        placeholder="Örn. Manisa"
        hint="Bölgenize uygun öneriler için kullanılır. Sonradan da ekleyebilirsiniz."
        value={province}
        onChangeText={setProvince}
        autoCapitalize="words"
        onSubmitEditing={submit}
      />
    </AuthScreen>
  );
}
