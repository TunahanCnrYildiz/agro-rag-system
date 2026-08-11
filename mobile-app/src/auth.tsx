/**
 * Local profile — deliberately NOT a real account system.
 *
 * NOTHING HERE LEAVES THE DEVICE. No password is collected, no credential is
 * stored, and no request is made to the backend. `register` writes a name (and
 * optionally a province) to AsyncStorage; `login` reads it back. That is the
 * whole mechanism.
 *
 * Why it is built this way, so nobody "upgrades" it by accident: the backend
 * has no user table, no authentication and no rate limit, and its CORS is still
 * open. Collecting real passwords in front of that would create a credential
 * store this project cannot yet protect, and a KVKK obligation nobody has taken
 * on. Emirhan asked for login/register and said a dummy was acceptable; this is
 * that dummy, and it is honest about being one.
 *
 * When real accounts arrive they belong on the server, behind authentication
 * and rate limiting, and this file gets replaced rather than extended.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

const STORAGE_KEY = "eta.profile.v1";

export type Profile = {
  name: string;
  /** Optional. Free text today; the assistant reads the province from the
   *  conversation itself, so this is for display until the server-side context
   *  work is deployed. */
  province?: string;
};

type AuthState = {
  /** null while the stored profile is still being read. */
  profile: Profile | null;
  /** False until the first read finishes, so the router does not redirect on a
   *  value it has not loaded yet — that flash is the classic bug in this shape. */
  ready: boolean;
  signUp: (profile: Profile) => Promise<void>;
  signIn: (name: string) => Promise<boolean>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        if (!cancelled && raw) {
          const parsed = JSON.parse(raw);
          // Tolerate anything that is not the shape we wrote: a corrupt value
          // must land the user on the sign-in screen, never crash the app.
          if (parsed && typeof parsed.name === "string" && parsed.name) {
            setProfile({ name: parsed.name, province: parsed.province });
          }
        }
      } catch {
        // Unreadable storage is treated as "no profile".
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signUp = useCallback(async (next: Profile) => {
    const clean: Profile = {
      name: next.name.trim(),
      province: next.province?.trim() || undefined,
    };
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(clean));
    setProfile(clean);
  }, []);

  const signIn = useCallback(async (name: string) => {
    // There is no credential to check against. "Signing in" means: is there a
    // profile on this device with that name? Anything else would be pretending
    // to verify something.
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    try {
      const parsed = JSON.parse(raw);
      if (
        parsed?.name &&
        parsed.name.trim().toLocaleLowerCase("tr") ===
          name.trim().toLocaleLowerCase("tr")
      ) {
        setProfile({ name: parsed.name, province: parsed.province });
        return true;
      }
    } catch {
      // fall through
    }
    return false;
  }, []);

  const signOut = useCallback(async () => {
    setProfile(null);
    // The stored profile is left in place on purpose, so signing back in works
    // without retyping. "Profili sil" on the home screen is what removes it.
  }, []);

  const value = useMemo(
    () => ({ profile, ready, signUp, signIn, signOut }),
    [profile, ready, signUp, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Remove the stored profile entirely. Separate from signOut so "log out" and
 *  "delete my data" stay distinguishable. */
export async function forgetProfile(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
}
