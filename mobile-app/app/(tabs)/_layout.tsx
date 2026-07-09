import { Platform } from "react-native";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors } from "../../src/theme";

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  // On web there's no OS safe-area inset, so the bar collapses to its base
  // height and the icon+label barely fit (labels clip at the bottom). Give web
  // an explicit, comfortable height; native keeps using the device's real
  // bottom inset.
  const isWeb = Platform.OS === "web";
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.green,
        tabBarInactiveTintColor: "#9aa393",
        tabBarStyle: {
          paddingBottom: isWeb ? 10 : Math.max(4, insets.bottom),
          paddingTop: isWeb ? 6 : 4,
          height: isWeb ? 64 : 54 + insets.bottom,
        },
        tabBarLabelStyle: { fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Ana Sayfa",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="products"
        options={{
          title: "Ürünler",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="leaf-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="articles"
        options={{
          title: "Akademi",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="book-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="chat"
        options={{
          title: "Asistan",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="chatbubble-ellipses-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
