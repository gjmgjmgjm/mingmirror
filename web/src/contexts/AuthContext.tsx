import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  changeAuthPassword,
  fetchAuthMe,
  linkAuthDevice,
  loginAccount,
  logoutAccount,
  registerAccount,
  type AuthUserDto,
} from "../api/client";
import {
  clearSession,
  getSessionToken,
  getStoredUser,
  setSession,
  type AuthUser,
} from "../lib/auth";
import { getDeviceId } from "../lib/analytics";

interface AuthContextValue {
  user: AuthUser | null;
  token: string;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    displayName?: string
  ) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  changePassword: (oldPw: string, newPw: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function toUser(dto: AuthUserDto): AuthUser {
  return {
    id: dto.id,
    email: dto.email,
    display_name: dto.display_name,
    created_at: dto.created_at,
    updated_at: dto.updated_at,
    is_active: dto.is_active,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [token, setToken] = useState<string>(() => getSessionToken());
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const t = getSessionToken();
    if (!t) {
      setUser(null);
      setToken("");
      setLoading(false);
      return;
    }
    try {
      const me = await fetchAuthMe();
      const u = toUser(me.user);
      setUser(u);
      setToken(t);
      setSession(t, u);
      // Keep device linked for entitlement merge
      try {
        await linkAuthDevice(getDeviceId());
      } catch {
        /* ignore */
      }
    } catch {
      clearSession();
      setUser(null);
      setToken("");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginAccount({
      email,
      password,
      device_id: getDeviceId(),
    });
    const u = toUser(res.user);
    setSession(res.token, u, res.expires_at);
    setUser(u);
    setToken(res.token);
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const res = await registerAccount({
        email,
        password,
        display_name: displayName || "",
        device_id: getDeviceId(),
      });
      const u = toUser(res.user);
      setSession(res.token, u, res.expires_at);
      setUser(u);
      setToken(res.token);
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await logoutAccount();
    } catch {
      /* ignore */
    }
    clearSession();
    setUser(null);
    setToken("");
  }, []);

  const changePassword = useCallback(async (oldPw: string, newPw: string) => {
    const res = await changeAuthPassword({
      old_password: oldPw,
      new_password: newPw,
    });
    const current = getStoredUser();
    if (res.token && current) {
      setSession(res.token, current, res.expires_at);
      setToken(res.token);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      login,
      register,
      logout,
      refresh,
      changePassword,
    }),
    [user, token, loading, login, register, logout, refresh, changePassword]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// oxlint-disable-next-line react/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
