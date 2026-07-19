/**
 * Session token storage for MingMirror account system.
 */

const TOKEN_KEY = "mingmirror_session_token_v1";
const USER_KEY = "mingmirror_user_v1";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  created_at?: number;
  updated_at?: number;
  is_active?: boolean;
}

export function getSessionToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setSession(
  token: string,
  user: AuthUser | null,
  expiresAt?: number
): void {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
    if (user) {
      localStorage.setItem(
        USER_KEY,
        JSON.stringify({ ...user, expires_at: expiresAt || 0 })
      );
    } else {
      localStorage.removeItem(USER_KEY);
    }
  } catch {
    // private mode
  }
}

export function clearSession(): void {
  setSession("", null);
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function authHeaders(): Record<string, string> {
  const token = getSessionToken();
  if (!token) return {};
  return {
    Authorization: `Bearer ${token}`,
    "X-Session-Token": token,
  };
}
