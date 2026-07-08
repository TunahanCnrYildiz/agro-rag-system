import React from "react";
import {
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { ScreenHeader } from "../../src/ScreenHeader";
import { colors } from "../../src/theme";
import { openExternalUrl } from "../../src/openExternalUrl";

const HERO_IMAGE = require("../../assets/logo-wordmark.png");
const SITE_URL = "https://www.ekolojiktarim.com.tr/";

const STATS = [
  { value: "1800+", label: "Temsilcilik" },
  { value: "60+", label: "Ürün" },
  { value: "33", label: "Yıllık Üretim Tecrübesi" },
  { value: "25+", label: "Ülkeye İhracat" },
];

export default function HomeScreen() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <ScreenHeader title="Ekolojik Tarım A.Ş." />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <Image
            source={HERO_IMAGE}
            style={styles.heroLogo}
            resizeMode="contain"
          />
          <Text style={styles.heroTitle}>
            Doğadan İlhamla Geleceği Şekillendiriyoruz
          </Text>
          <Text style={styles.heroText}>
            1989 yılında temelleri atılan Ekolojik Tarım A.Ş., bitki besleme
            sektöründe yenilikçi ve sürdürülebilir çözümler üreterek 29
            ülkeye ihracat yapan bir dünya firması haline gelmiştir.
          </Text>
        </View>

        <View style={styles.statsGrid}>
          {STATS.map((s) => (
            <View key={s.label} style={styles.statCard}>
              <Text style={styles.statValue}>{s.value}</Text>
              <Text style={styles.statLabel}>{s.label}</Text>
            </View>
          ))}
        </View>

        <Text style={styles.sectionTitle}>Keşfedin</Text>

        <TouchableOpacity
          style={styles.quickLink}
          onPress={() => router.push("/products")}
        >
          <View style={[styles.quickIcon, { backgroundColor: colors.green }]}>
            <Ionicons name="leaf-outline" size={22} color="#fff" />
          </View>
          <View style={styles.quickTextWrap}>
            <Text style={styles.quickTitle}>Ürün Kataloğu</Text>
            <Text style={styles.quickSubtitle}>
              Organik gübreler, mikro/makro besinler ve daha fazlası
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#9aa393" />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.quickLink}
          onPress={() => router.push("/articles")}
        >
          <View style={[styles.quickIcon, { backgroundColor: colors.greenLight }]}>
            <Ionicons name="book-outline" size={22} color="#fff" />
          </View>
          <View style={styles.quickTextWrap}>
            <Text style={styles.quickTitle}>Tarım Akademisi</Text>
            <Text style={styles.quickSubtitle}>
              Bitki besleme ve toprak sağlığı hakkında eğitici içerikler
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#9aa393" />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.quickLink}
          onPress={() => router.push("/chat")}
        >
          <View style={[styles.quickIcon, { backgroundColor: colors.dark }]}>
            <Ionicons name="chatbubble-ellipses-outline" size={22} color="#fff" />
          </View>
          <View style={styles.quickTextWrap}>
            <Text style={styles.quickTitle}>Yapay Zeka Asistanı</Text>
            <Text style={styles.quickSubtitle}>
              Bitkileriniz hakkında sorularınızı yanıtlayalım
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#9aa393" />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.siteLink}
          onPress={() => openExternalUrl(SITE_URL)}
        >
          <Text style={styles.siteLinkText}>Web Sitemizi Ziyaret Edin</Text>
          <Ionicons name="open-outline" size={16} color={colors.green} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 16, paddingBottom: 32 },
  hero: {
    backgroundColor: colors.white,
    borderRadius: 16,
    padding: 20,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
  },
  heroLogo: { width: 160, height: 26, marginBottom: 14 },
  heroTitle: {
    fontSize: 17,
    fontWeight: "700",
    color: colors.dark,
    textAlign: "center",
    marginBottom: 8,
  },
  heroText: {
    fontSize: 13,
    lineHeight: 19,
    color: "#565f52",
    textAlign: "center",
  },
  statsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginTop: 16,
  },
  statCard: {
    flexBasis: "47%",
    flexGrow: 1,
    backgroundColor: colors.white,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
  },
  statValue: { fontSize: 22, fontWeight: "800", color: colors.green },
  statLabel: { fontSize: 11.5, color: "#565f52", marginTop: 2, textAlign: "center" },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: colors.dark,
    marginTop: 24,
    marginBottom: 10,
  },
  quickLink: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 12,
    padding: 12,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.bubbleBotBorder,
    gap: 12,
  },
  quickIcon: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
  },
  quickTextWrap: { flex: 1 },
  quickTitle: { fontSize: 13.5, fontWeight: "700", color: colors.dark },
  quickSubtitle: { fontSize: 11.5, color: "#565f52", marginTop: 2 },
  siteLink: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginTop: 14,
    padding: 10,
  },
  siteLinkText: { color: colors.green, fontSize: 13, fontWeight: "600" },
});
