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
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "./theme";
import { useAuth } from "./auth";

export function ProfileCard() {
  const { profile } = useAuth();
  if (!profile) return null;

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
          {[profile.province, profile.crops].filter(Boolean).join(" · ") ||
            "İl bilgisi eklenmedi"}
        </Text>
      </View>
      <Pressable
        style={styles.actions}
        onPress={() => router.push("/profile")}
        hitSlop={8}
      >
        <Text style={styles.action}>Profilim</Text>
        <Ionicons name="chevron-forward" size={16} color={colors.green} />
      </Pressable>
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
  actions: { flexDirection: "row", alignItems: "center", gap: 2 },
  action: { color: colors.green, fontSize: 13, fontWeight: "600" },
  danger: { color: "#b3261e" },
});
