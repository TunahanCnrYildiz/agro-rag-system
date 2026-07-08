import React, { useMemo, useRef, useState } from "react";
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
  const chipsScrollRef = useRef<ScrollView>(null);
  const chipOffsets = useRef<Record<string, number>>({});

  // "Tüm Ürünler" is the source site's default label for uncategorized
  // products, not a real category - it's redundant with our own "Tümü"
  // filter, so it's dropped from the chip list (the product itself still
  // shows up under "Tümü").
  const categories = useMemo(
    () =>
      Array.from(new Set(data.map((p) => p.category)))
        .filter((c) => c !== "Tüm Ürünler")
        .sort(),
    [data]
  );
  const filtered = activeCategory
    ? data.filter((p) => p.category === activeCategory)
    : data;

  function selectCategory(key: string | null) {
    setActiveCategory(key);
    const x = chipOffsets.current[key ?? "__all__"];
    if (x !== undefined) {
      chipsScrollRef.current?.scrollTo({ x: Math.max(0, x - 20), animated: true });
    }
  }

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
            ref={chipsScrollRef}
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.chipsRow}
            contentContainerStyle={styles.chipsContent}
          >
            <TouchableOpacity
              style={[styles.chip, !activeCategory && styles.chipActive]}
              onPress={() => selectCategory(null)}
              onLayout={(e) => {
                chipOffsets.current["__all__"] = e.nativeEvent.layout.x;
              }}
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
                onPress={() => selectCategory(c)}
                onLayout={(e) => {
                  chipOffsets.current[c] = e.nativeEvent.layout.x;
                }}
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
  chipsRow: {
    flexGrow: 0,
    flexShrink: 0,
    borderBottomWidth: 1,
    borderBottomColor: "#e6e6e6",
  },
  chipsContent: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
    alignItems: "center",
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 18,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.greenLight,
  },
  chipActive: { backgroundColor: colors.green, borderColor: colors.green },
  // Explicit lineHeight so the chip Text reserves enough vertical room for
  // tall Turkish glyphs (ü, ğ, İ) - without it Android crops the text.
  chipText: { fontSize: 12, lineHeight: 18, color: colors.dark },
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
    maxWidth: "47%",
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
