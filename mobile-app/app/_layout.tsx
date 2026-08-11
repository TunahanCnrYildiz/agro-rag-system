import { useEffect } from "react";
import { View } from "react-native";
import { Stack, useRouter, useSegments } from "expo-router";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { AuthProvider, useAuth } from "../src/auth";
import { colors } from "../src/theme";

/**
 * Sends the user to the auth screens when there is no local profile, and out of
 * them once there is.
 *
 * The `ready` gate matters: AsyncStorage is read asynchronously, so for the
 * first frames `profile` is null even for a user who has one. Redirecting on
 * that would bounce a returning user through the sign-in screen every launch.
 */
function AuthGate() {
  const { profile, ready } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    const inAuth = segments[0] === "(auth)";
    if (!profile && !inAuth) {
      router.replace("/(auth)/register");
    } else if (profile && inAuth) {
      router.replace("/(tabs)");
    }
  }, [ready, profile, segments, router]);

  // Hold a plain background until the stored profile has been read, so neither
  // the tabs nor the sign-in screen flashes before we know which is correct.
  if (!ready) return <View style={{ flex: 1, backgroundColor: colors.bg }} />;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="product/[id]" options={{ headerShown: true, title: "Ürün" }} />
      <Stack.Screen name="article/[id]" options={{ headerShown: true, title: "Makale" }} />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <AuthProvider>
        <AuthGate />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
