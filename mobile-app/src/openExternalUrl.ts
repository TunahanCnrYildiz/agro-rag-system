import { Linking, Platform } from "react-native";

// On web, Linking.openURL() calls window.open(url, '_blank'), which popup
// blockers frequently reject - including in automated/preview browser
// contexts, even for real clicks. Same-tab navigation via location.href is
// never subject to popup blocking, so use that on web instead. Native
// platforms are unaffected (Linking.openURL uses the OS's own URL handling).
export function openExternalUrl(url: string) {
  if (Platform.OS === "web") {
    window.location.href = url;
  } else {
    Linking.openURL(url);
  }
}
