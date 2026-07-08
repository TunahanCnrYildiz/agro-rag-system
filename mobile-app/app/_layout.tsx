import { Stack } from "expo-router";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="product/[id]" options={{ headerShown: true, title: "Ürün" }} />
        <Stack.Screen name="article/[id]" options={{ headerShown: true, title: "Makale" }} />
      </Stack>
    </SafeAreaProvider>
  );
}
