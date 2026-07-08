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
import { useLocalSearchParams } from "expo-router";
import { colors } from "../../src/theme";
import { useProducts } from "../../src/data";
import { openExternalUrl } from "../../src/openExternalUrl";

export default function ProductDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const url = decodeURIComponent(id ?? "");
  const { data, loading } = useProducts();
  const product = data.find((p) => p.source_url === url);

  if (loading) {
    return (
      <View style={styles.centerBox}>
        <ActivityIndicator color={colors.green} />
      </View>
    );
  }

  if (!product) {
    return (
      <View style={styles.centerBox}>
        <Text style={styles.errorText}>Ürün bulunamadı.</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {product.image_url ? (
        <Image source={{ uri: product.image_url }} style={styles.image} />
      ) : null}
      <Text style={styles.category}>{product.category}</Text>
      <Text style={styles.title}>{product.product_name}</Text>
      <Text style={styles.description}>{product.description}</Text>

      <TouchableOpacity
        style={styles.siteButton}
        onPress={() => openExternalUrl(product.source_url)}
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
    height: 260,
    borderRadius: 14,
    backgroundColor: "#eef2ea",
    marginBottom: 16,
  },
  category: { fontSize: 12, color: colors.green, fontWeight: "700" },
  title: { fontSize: 19, fontWeight: "800", color: colors.dark, marginTop: 4, marginBottom: 12 },
  description: { fontSize: 13.5, lineHeight: 20, color: "#3a3f36" },
  siteButton: {
    marginTop: 22,
    backgroundColor: colors.green,
    borderRadius: 24,
    paddingVertical: 13,
    alignItems: "center",
  },
  siteButtonText: { color: "#fff", fontWeight: "700", fontSize: 13.5 },
});
