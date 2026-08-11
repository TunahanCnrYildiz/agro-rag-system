/**
 * Local profile with an ID and a password — deliberately NOT a real account
 * system, and the difference matters.
 *
 * NOTHING HERE LEAVES THE DEVICE. The password is never transmitted, and it is
 * never stored: what is stored is a random salt and SHA-256(salt + password).
 * Signing in re-derives that digest and compares it. There is no server call
 * anywhere in this file.
 *
 * WHY IT IS BUILT THIS WAY, so nobody "upgrades" it by accident: the backend
 * has no user table, no authentication and no rate limit, and its CORS is still
 * open. Sending real credentials to that would create a credential store this
 * project cannot protect and a KVKK obligation nobody has taken on. When real
 * accounts arrive they belong on the server, behind authentication and rate
 * limiting, and this file gets REPLACED rather than extended.
 *
 * ON THE HASHING, stated honestly: SHA-256 with a salt is not a password KDF.
 * A real credential store needs bcrypt/scrypt/argon2, which are deliberately
 * slow so that a stolen database cannot be brute-forced. That is not what this
 * is. Salting and digesting here does exactly two useful things — it keeps the
 * password out of plaintext storage, and it keeps a password the user has
 * reused elsewhere from being readable by anything that can read app storage.
 * It guards nothing else, because there is nothing else here to guard.
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
import * as Crypto from "expo-crypto";

const STORAGE_KEY = "eta.profile.v2";

/** What the rest of the app may see. The salt and digest never appear here. */
export type Profile = {
  name: string;
  userId: string;
  email: string;
  province?: string;
};

type StoredProfile = Profile & { salt: string; digest: string };

type SignUpInput = {
  name: string;
  userId: string;
  email: string;
  password: string;
  province?: string;
};

type AuthState = {
  profile: Profile | null;
  /** False until the stored profile has been read. The router must not redirect
   *  before this flips, or a returning user is bounced to sign-in every launch. */
  ready: boolean;
  /** True when a profile exists on this device, so the app can open on the
   *  sign-in screen rather than the sign-up one. */
  hasAccount: boolean;
  signUp: (input: SignUpInput) => Promise<void>;
  signIn: (userId: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

/** Turkish-aware, case-insensitive comparison for the login ID. */
const foldId = (s: string) => s.trim().toLocaleLowerCase("tr");

async function digest(salt: string, password: string): Promise<string> {
  return Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    `${salt}:${password}`,
  );
}

async function newSalt(): Promise<string> {
  const bytes = await Crypto.getRandomBytesAsync(16);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

async function readStored(): Promise<StoredProfile | null> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    // Anything not matching the shape we wrote is treated as "no profile" — a
    // corrupt value must land the user on sign-in, never crash the app.
    if (
      p &&
      typeof p.name === "string" &&
      typeof p.userId === "string" &&
      typeof p.salt === "string" &&
      typeof p.digest === "string" &&
      p.name &&
      p.userId
    ) {
      return p as StoredProfile;
    }
  } catch {
    // unreadable storage == no profile
  }
  return null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [hasAccount, setHasAccount] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await readStored();
      if (!cancelled) {
        // A stored profile does NOT sign the user in. They still enter their ID
        // and password — otherwise the password would be decoration.
        setHasAccount(stored !== null);
        setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signUp = useCallback(async (input: SignUpInput) => {
    const salt = await newSalt();
    const stored: StoredProfile = {
      name: input.name.trim(),
      userId: input.userId.trim(),
      email: input.email.trim(),
      province: input.province?.trim() || undefined,
      salt,
      digest: await digest(salt, input.password),
    };
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    setHasAccount(true);
    setProfile({
      name: stored.name,
      userId: stored.userId,
      email: stored.email,
      province: stored.province,
    });
  }, []);

  const signIn = useCallback(async (userId: string, password: string) => {
    const stored = await readStored();
    if (!stored) return false;
    if (foldId(stored.userId) !== foldId(userId)) return false;
    const attempt = await digest(stored.salt, password);
    // Both halves must match. A wrong ID and a wrong password are reported to
    // the user identically, so the screen does not confirm which IDs exist.
    if (attempt !== stored.digest) return false;
    setProfile({
      name: stored.name,
      userId: stored.userId,
      // Tolerated as absent: profiles created before the e-mail field existed
      // must still open rather than being thrown away.
      email: stored.email ?? "",
      province: stored.province,
    });
    return true;
  }, []);

  const signOut = useCallback(async () => {
    // The stored profile stays; signing back in needs the ID and password
    // again. "Profili sil" is what removes it.
    setProfile(null);
  }, []);

  const value = useMemo(
    () => ({ profile, ready, hasAccount, signUp, signIn, signOut }),
    [profile, ready, hasAccount, signUp, signIn, signOut],
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
