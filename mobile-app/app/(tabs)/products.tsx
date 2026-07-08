import React, { useMemo, useState } from "react";
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
import { useProducts } from "../../src/data";

export default function ProductsScreen() {
  const { data, loading, error } = useProducts();
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const router = useRouter();

  const categories = useMemo(
    () => Array.from(new Set(data.map((p) => p.category))).sort(),
    [data]
  );
  const filtered = activeCategory
    ? data.filter((p) => p.category === activeCategory)
    : data;

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <ScreenHeader title="Ürün Kataloğu" />

      {loading && (
        <View style={styles.centerBox}>
          <ActivityIndicator color={colors.green} />
        </View>
      )}
      {error && !loading && (
        <View style={styles.centerBox}>
          <Text style={styles.errorText}>
            Ürünler yüklenemedi. API sunucusunun çalıştığından emin olun.
          </Text>
        </View>
      )}

      {!loading && !error && (
        <>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.chipsRow}
            contentContainerStyle={styles.chipsContent}
          >
            <TouchableOpacity
              style={[styles.chip, !activeCategory && styles.chipActive]}
              onPress={() => setActiveCategory(null)}
            >
              <Text
                style={[
                  styles.chipText,
                  !activeCategory && styles.chipTextActive,
                ]}
              >
                Tümü
              </Text>
            </TouchableOpacity>
            {categories.map((c) => (
              <TouchableOpacity
                key={c}
                style={[styles.chip, activeCategory === c && styles.chipActive]}
                onPress={() => setActiveCategory(c)}
              >
                <Text
                  style={[
                    styles.chipText,
                    activeCategory === c && styles.chipTextActive,
                  ]}
                >
                  {c}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <ScrollView contentContainerStyle={styles.grid}>
            {filtered.map((p) => (
              <TouchableOpacity
                key={p.source_url}
                style={styles.card}
                onPress={() =>
                  router.push({
                    pathname: "/product/[id]",
                    params: { id: encodeURIComponent(p.source_url) },
                  })
                }
              >
                {p.image_url ? (
                  <Image source={{ uri: p.image_url }} style={styles.cardImage} />
                ) : (
                  <View style={[styles.cardImage, styles.cardImagePlaceholder]} />
                )}
                <Text style={styles.cardCategory}>{p.category}</Text>
                <Text style={styles.cardTitle} numberOfLines={2}>
                  {p.product_name}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  centerBox: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  errorText: { color: "#a33", textAlign: "center", fontSize: 13 },
  chipsRow: { flexGrow: 0, borderBottomWidth: 1, borderBottomColor: "#e6e6e6" },
  chipsContent: { paddingHorizontal: 12, paddingVertical: 10, gap: 8 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 16,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.greenLight,
  },
  chipActive: { backgroundColor: colors.green, borderColor: colors.green },
  chipText: { fontSize: 12, color: colors.dark },
  chipTextActive: { color: "#fff", fontWeight: "600" },
  grid: {
    padding: 12,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  card: {
    flexBasis: "47%",
    flexGrow: 1,
    backgroundColor: colors.white,
    borderRadius: 12,
    padding: 10,
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
  },
  cardImage: { width: "100%", height: 110, borderRadius: 8, backgroundColor: "#eef2ea" },
  cardImagePlaceholder: {},
  cardCategory: { fontSize: 10.5, color: colors.green, marginTop: 8, fontWeight: "600" },
  cardTitle: { fontSize: 12.5, color: colors.dark, marginTop: 3, fontWeight: "600" },
});
