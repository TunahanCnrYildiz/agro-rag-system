/**
 * The signed-in user's local profile, with the two actions that matter:
 * sign out (keeps the profile so signing back in is one tap) and delete
 * (removes it from the device entirely).
 *
 * Both exist because they are different promises. "Çıkış" is a convenience;
 * "Profili sil" is the one that actually removes the data, and a user who wants
 * their information gone should not have to guess which button does that.
 */
import React from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "./theme";
import { forgetProfile, useAuth } from "./auth";

export function ProfileCard() {
  const { profile, signOut } = useAuth();
  if (!profile) return null;

  async function leave(alsoForget: boolean) {
    if (alsoForget) await forgetProfile();
    await signOut();
    router.replace("/(auth)/login");
  }

  function confirmDelete() {
    Alert.alert(
      "Profili sil",
      "Bu cihazdaki profil bilgileriniz silinecek. Devam edilsin mi?",
      [
        { text: "Vazgeç", style: "cancel" },
        { text: "Sil", style: "destructive", onPress: () => leave(true) },
      ],
    );
  }

  return (
    <View style={styles.card}>
      <Ionicons name="person-circle-outline" size={38} color={colors.green} />
      <View style={styles.who}>
        <Text style={styles.name} numberOfLines={1}>
          Merhaba, {profile.name}
        </Text>
        {/* What is stored is shown, so a user can see their own record rather
            than having to trust a claim about it. */}
        <Text style={styles.sub} numberOfLines={1}>
          {[profile.province, profile.email].filter(Boolean).join(" · ") ||
            "İl bilgisi eklenmedi"}
        </Text>
      </View>
      <View style={styles.actions}>
        <Pressable onPress={() => leave(false)} hitSlop={8}>
          <Text style={styles.action}>Çıkış</Text>
        </Pressable>
        <Pressable onPress={confirmDelete} hitSlop={8}>
          <Text style={[styles.action, styles.danger]}>Profili sil</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 16,
  },
  who: { flex: 1, minWidth: 0 },
  name: { color: colors.dark, fontSize: 15, fontWeight: "700" },
  sub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  actions: { alignItems: "flex-end", gap: 6 },
  action: { color: colors.green, fontSize: 13, fontWeight: "600" },
  danger: { color: "#b3261e" },
});
