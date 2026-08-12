/**
 * Password recovery.
 *
 * THIS GENUINELY WORKS — it is not a mock-up. The e-mail is checked against the
 * stored profile, a new password is generated and saved, and the user can sign
 * in with it immediately.
 *
 * The one part that is not final is DELIVERY. There is no server to send mail
 * from, so the new password is shown on screen and the screen says so. When the
 * backend lands, the only change here is that the password stops being displayed
 * and starts being e-mailed; the flow, the validation and the copy stay.
 *
 * Showing it on screen weakens nothing that is currently protected: the profile
 * lives on this device, and anyone holding the unlocked phone could already
 * delete it and make a new one. It would be a real weakness the moment accounts
 * become server-side, which is exactly when this display goes away.
 */
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { AuthScreen, Field, authStyles } from "../../src/AuthForm";
import { colors } from "../../src/theme";
import { useAuth } from "../../src/auth";

export default function ForgotPasswordScreen() {
  const { resetPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newPassword, setNewPassword] = useState<string | null>(null);

  async function submit() {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Geçerli bir e-posta adresi yazın.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const pw = await resetPassword(email);
      if (pw) {
        setNewPassword(pw);
      } else {
        setError("Bu e-posta adresiyle kayıtlı bir profil bulunamadı.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (newPassword) {
    return (
      <AuthScreen
        title="Yeni şifreniz hazır"
        subtitle="Bu şifreyle giriş yapabilirsiniz. Giriş yaptıktan sonra Profilim ekranından değiştirmenizi öneririz."
        submitLabel="Giriş ekranına dön"
        onSubmit={() => router.replace("/(auth)/login")}
        footer={null}
      >
        <View style={styles.pwBox}>
          <Text style={styles.pwLabel}>Yeni şifreniz</Text>
          <Text selectable style={styles.pw}>
            {newPassword}
          </Text>
        </View>
        <Text style={styles.deliveryNote}>
          E-posta gönderimi henüz aktif olmadığı için şifreniz burada
          gösteriliyor. Ekrandan ayrılmadan önce not alın.
        </Text>
      </AuthScreen>
    );
  }

  return (
    <AuthScreen
      title="Şifremi unuttum"
      subtitle="Profilinizde kayıtlı e-posta adresini girin; size yeni bir şifre oluşturalım."
      error={error}
      submitLabel={busy ? "Oluşturuluyor..." : "Yeni şifre oluştur"}
      onSubmit={submit}
      disabled={busy}
      footer={
        <Pressable onPress={() => router.replace("/(auth)/login")}>
          <Text style={[authStyles.hint, { textAlign: "center", marginTop: 16 }]}>
            Giriş ekranına dön
          </Text>
        </Pressable>
      }
    >
      <Field
        label="E-posta"
        placeholder="Profilinizdeki e-posta adresi"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
        onSubmitEditing={submit}
      />
    </AuthScreen>
  );
}

const styles = StyleSheet.create({
  pwBox: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.green,
    borderRadius: 12,
    paddingVertical: 18,
    alignItems: "center",
    marginBottom: 12,
  },
  pwLabel: { color: colors.muted, fontSize: 12, marginBottom: 6 },
  pw: {
    color: colors.dark,
    fontSize: 26,
    fontWeight: "700",
    letterSpacing: 3,
  },
  deliveryNote: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17,
    textAlign: "center",
    marginBottom: 6,
  },
});
