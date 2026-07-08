import React from "react";
import { Image, StyleSheet, Text, View } from "react-native";
import { colors } from "./theme";

const LOGO = require("../assets/logo-wordmark.png");

export function ScreenHeader({ title }: { title: string }) {
  return (
    <View style={styles.header}>
      <Image
        source={LOGO}
        style={styles.logo}
        resizeMode="contain"
        tintColor="#ffffff"
      />
      <Text style={styles.title}>{title}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    backgroundColor: colors.green,
    paddingHorizontal: 16,
    paddingVertical: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  logo: { width: 130, height: 21 },
  title: { color: "#fff", fontSize: 15, fontWeight: "700" },
});
