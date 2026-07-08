import React from "react";
import {
  ActivityIndicator,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { ScreenHeader } from "../../src/ScreenHeader";
import { colors } from "../../src/theme";
import { useArticles } from "../../src/data";

export default function ArticlesScreen() {
  const { data, loading, error } = useArticles();
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <ScreenHeader title="Tarım Akademisi" />

      {loading && (
        <View style={styles.centerBox}>
          <ActivityIndicator color={colors.green} />
        </View>
      )}
      {error && !loading && (
        <View style={styles.centerBox}>
          <Text style={styles.errorText}>
            Makaleler yüklenemedi. API sunucusunun çalıştığından emin olun.
          </Text>
        </View>
      )}

      {!loading && !error && (
        <ScrollView contentContainerStyle={styles.list}>
          {data.map((a) => (
            <TouchableOpacity
              key={a.source_url}
              style={styles.card}
              onPress={() =>
                router.push({
                  pathname: "/article/[id]",
                  params: { id: encodeURIComponent(a.source_url) },
                })
              }
            >
              {a.image_url ? (
                <Image source={{ uri: a.image_url }} style={styles.thumb} />
              ) : (
                <View style={[styles.thumb, styles.thumbPlaceholder]} />
              )}
              <View style={styles.cardText}>
                <Text style={styles.cardCategory}>{a.category} · {a.date}</Text>
                <Text style={styles.cardTitle} numberOfLines={3}>
                  {a.title}
                </Text>
              </View>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  centerBox: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  errorText: { color: "#a33", textAlign: "center", fontSize: 13 },
  list: { padding: 12, gap: 10 },
  card: {
    flexDirection: "row",
    backgroundColor: colors.white,
    borderRadius: 12,
    padding: 10,
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
    gap: 12,
    marginBottom: 10,
  },
  thumb: { width: 88, height: 88, borderRadius: 10, backgroundColor: "#eef2ea" },
  thumbPlaceholder: {},
  cardText: { flex: 1, justifyContent: "center" },
  cardCategory: { fontSize: 10.5, color: colors.green, fontWeight: "600", marginBottom: 4 },
  cardTitle: { fontSize: 13, color: colors.dark, fontWeight: "600", lineHeight: 18 },
});
