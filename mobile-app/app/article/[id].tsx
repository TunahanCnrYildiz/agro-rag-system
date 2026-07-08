import React from "react";
import {
  ActivityIndicator,
  Image,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { colors } from "../../src/theme";
import { useArticles } from "../../src/data";

export default function ArticleDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const url = decodeURIComponent(id ?? "");
  const { data, loading } = useArticles();
  const article = data.find((a) => a.source_url === url);

  if (loading) {
    return (
      <View style={styles.centerBox}>
        <ActivityIndicator color={colors.green} />
      </View>
    );
  }

  if (!article) {
    return (
      <View style={styles.centerBox}>
        <Text style={styles.errorText}>Makale bulunamadı.</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {article.image_url ? (
        <Image source={{ uri: article.image_url }} style={styles.image} />
      ) : null}
      <Text style={styles.category}>
        {article.category} · {article.date}
      </Text>
      <Text style={styles.title}>{article.title}</Text>
      <Text style={styles.body}>{article.content || article.excerpt}</Text>

      <TouchableOpacity
        style={styles.siteButton}
        onPress={() => Linking.openURL(article.source_url)}
      >
        <Text style={styles.siteButtonText}>Sitede Görüntüle</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  centerBox: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  errorText: { color: "#a33", fontSize: 13 },
  content: { padding: 16, paddingBottom: 40 },
  image: {
    width: "100%",
    height: 200,
    borderRadius: 14,
    backgroundColor: "#eef2ea",
    marginBottom: 16,
  },
  category: { fontSize: 12, color: colors.green, fontWeight: "700" },
  title: { fontSize: 18, fontWeight: "800", color: colors.dark, marginTop: 6, marginBottom: 12 },
  body: { fontSize: 13.5, lineHeight: 21, color: "#3a3f36" },
  siteButton: {
    marginTop: 22,
    backgroundColor: colors.green,
    borderRadius: 24,
    paddingVertical: 13,
    alignItems: "center",
  },
  siteButtonText: { color: "#fff", fontWeight: "700", fontSize: 13.5 },
});
