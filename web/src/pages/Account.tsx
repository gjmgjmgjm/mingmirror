import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  forgotPassword,
  requestEmailVerify,
  resetPassword,
  verifyEmailToken,
} from "../api/client";
import { PageHeader, SectionCard, ErrorPanel } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import { setSession, type AuthUser } from "../lib/auth";
import { refreshEntitlementFromServer } from "../lib/entitlements";

export default function Account() {
  const { user, loading, login, register, logout, changePassword, refresh } =
    useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register" | "forgot">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [verifyTok, setVerifyTok] = useState("");
  const [resetTok, setResetTok] = useState("");
  const [resetNewPw, setResetNewPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email.trim(), password);
        setMsg("登录成功");
        void refreshEntitlementFromServer();
      } else if (mode === "register") {
        await register(email.trim(), password, displayName.trim());
        setMsg("注册成功。请完成邮箱验证（下方可填验证令牌）。");
        void refreshEntitlementFromServer();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
    } finally {
      setBusy(false);
    }
  };

  const onForgot = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      const res = await forgotPassword(email.trim());
      if (res.reset_token) {
        setResetTok(res.reset_token);
        setMsg(
          "已签发重置令牌（无 SMTP，已自动填入）。请设置新密码后提交。"
        );
      } else {
        setMsg(res.message || "若邮箱已注册，将收到重置指引。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
    } finally {
      setBusy(false);
    }
  };

  const onResetPw = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      const res = await resetPassword({
        token: resetTok.trim(),
        new_password: resetNewPw,
      });
      if (res.token && res.user) {
        const u: AuthUser = {
          id: res.user.id,
          email: res.user.email,
          display_name: res.user.display_name,
          email_verified: res.user.email_verified,
        };
        setSession(res.token, u, res.expires_at);
        await refresh();
        setMsg("密码已重置并自动登录");
        setMode("login");
        setResetNewPw("");
        void refreshEntitlementFromServer();
      } else {
        setMsg("密码已重置，请登录");
        setMode("login");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "重置失败");
    } finally {
      setBusy(false);
    }
  };

  const onChangePw = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      await changePassword(oldPw, newPw);
      setOldPw("");
      setNewPw("");
      setMsg("密码已更新，请使用新密码登录其他设备");
    } catch (err) {
      setError(err instanceof Error ? err.message : "修改失败");
    } finally {
      setBusy(false);
    }
  };

  const onRequestVerify = async () => {
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      const res = await requestEmailVerify();
      if (res.email_verify_token) {
        setVerifyTok(res.email_verify_token);
        setMsg("已签发验证令牌（无 SMTP，已填入下方）。请点「确认验证」。");
      } else {
        setMsg("验证邮件已排队（若已配置 SMTP）");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
    } finally {
      setBusy(false);
    }
  };

  const onConfirmVerify = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      await verifyEmailToken(verifyTok.trim());
      await refresh();
      setMsg("邮箱已验证");
      setVerifyTok("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证失败");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-lg p-6 text-sm text-ink-500">加载账号…</div>
    );
  }

  if (user) {
    return (
      <div className="mx-auto max-w-lg space-y-4 p-4 md:p-6">
        <PageHeader title="账号" subtitle="命镜账户 · 跨设备同步权益与命盘" />
        {error && <ErrorPanel>{error}</ErrorPanel>}
        {msg && (
          <p className="rounded-lg bg-jade/10 px-3 py-2 text-sm text-jade">{msg}</p>
        )}
        <SectionCard title="当前登录">
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-ink-500">邮箱</dt>
              <dd className="font-medium text-ink-800 dark:text-ink-100">
                {user.email}
                <span
                  className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    user.email_verified
                      ? "bg-jade/15 text-jade"
                      : "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                  }`}
                >
                  {user.email_verified ? "已验证" : "未验证"}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-ink-500">昵称</dt>
              <dd className="font-medium text-ink-800 dark:text-ink-100">
                {user.display_name || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-ink-500">用户 ID</dt>
              <dd className="font-mono text-xs text-ink-600">{user.id}</dd>
            </div>
          </dl>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-xl border border-ink-300 px-4 py-2 text-sm hover:bg-ink-100 dark:border-ink-600 dark:hover:bg-ink-800"
              onClick={() => void logout().then(() => navigate("/account"))}
            >
              退出登录
            </button>
            <Link
              to="/pricing"
              className="rounded-xl bg-vermilion/90 px-4 py-2 text-sm text-white hover:bg-vermilion"
            >
              套餐与权益
            </Link>
          </div>
        </SectionCard>

        {!user.email_verified && (
          <SectionCard title="验证邮箱">
            <p className="mb-3 text-xs text-ink-500">
              未配置 SMTP 时，点击「获取验证令牌」后在下方粘贴确认即可。
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void onRequestVerify()}
              className="mb-3 rounded-xl border border-jade/40 px-3 py-1.5 text-sm text-jade hover:bg-jade/10 disabled:opacity-50"
            >
              获取验证令牌
            </button>
            <form onSubmit={onConfirmVerify} className="space-y-3">
              <input
                type="text"
                placeholder="email_verify_token"
                value={verifyTok}
                onChange={(e) => setVerifyTok(e.target.value)}
                className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 font-mono text-xs dark:border-ink-600 dark:bg-ink-900"
                required
              />
              <button
                type="submit"
                disabled={busy}
                className="rounded-xl bg-jade px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                确认验证
              </button>
            </form>
          </SectionCard>
        )}

        <SectionCard title="修改密码">
          <form onSubmit={onChangePw} className="space-y-3">
            <input
              type="password"
              placeholder="当前密码"
              value={oldPw}
              onChange={(e) => setOldPw(e.target.value)}
              className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm dark:border-ink-600 dark:bg-ink-900"
              required
              minLength={8}
            />
            <input
              type="password"
              placeholder="新密码（至少 8 位）"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm dark:border-ink-600 dark:bg-ink-900"
              required
              minLength={8}
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-xl bg-ink-800 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-ink-200 dark:text-ink-900"
            >
              {busy ? "提交中…" : "更新密码"}
            </button>
          </form>
        </SectionCard>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-4 p-4 md:p-6">
      <PageHeader
        title="登录 / 注册"
        subtitle="注册后可将匿名设备权益合并到账号，跨浏览器使用"
      />
      {error && <ErrorPanel>{error}</ErrorPanel>}
      {msg && (
        <p className="rounded-lg bg-jade/10 px-3 py-2 text-sm text-jade">{msg}</p>
      )}
      <SectionCard
        title={
          mode === "login"
            ? "登录"
            : mode === "register"
              ? "注册"
              : "忘记密码"
        }
      >
        <div className="mb-3 flex flex-wrap gap-2 text-sm">
          {(
            [
              ["login", "登录"],
              ["register", "注册"],
              ["forgot", "忘记密码"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              className={`rounded-full px-3 py-1 ${
                mode === m
                  ? "bg-vermilion/15 text-vermilion"
                  : "text-ink-500"
              }`}
              onClick={() => setMode(m)}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === "forgot" ? (
          <div className="space-y-4">
            <form onSubmit={onForgot} className="space-y-3">
              <input
                type="email"
                placeholder="注册邮箱"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm dark:border-ink-600 dark:bg-ink-900"
                required
              />
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-xl bg-ink-800 px-4 py-2.5 text-sm text-white disabled:opacity-50 dark:bg-ink-200 dark:text-ink-900"
              >
                获取重置令牌
              </button>
            </form>
            <form onSubmit={onResetPw} className="space-y-3 border-t border-ink-200 pt-3 dark:border-ink-700">
              <p className="text-xs text-ink-500">用令牌设置新密码</p>
              <input
                type="text"
                placeholder="reset_token"
                value={resetTok}
                onChange={(e) => setResetTok(e.target.value)}
                className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 font-mono text-xs dark:border-ink-600 dark:bg-ink-900"
                required
              />
              <input
                type="password"
                placeholder="新密码（至少 8 位）"
                value={resetNewPw}
                onChange={(e) => setResetNewPw(e.target.value)}
                className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm dark:border-ink-600 dark:bg-ink-900"
                required
                minLength={8}
              />
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-xl bg-vermilion px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
              >
                重置并登录
              </button>
            </form>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-3">
            {mode === "register" && (
              <input
                type="text"
                placeholder="昵称（可选）"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm dark:border-ink-600 dark:bg-ink-900"
              />
            )}
            <input
              type="email"
              placeholder="邮箱"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm dark:border-ink-600 dark:bg-ink-900"
              required
              autoComplete="email"
            />
            <input
              type="password"
              placeholder="密码（至少 8 位）"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-ink-300 bg-white px-3 py-2 text-sm dark:border-ink-600 dark:bg-ink-900"
              required
              minLength={8}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-vermilion px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy
                ? "请稍候…"
                : mode === "login"
                  ? "登录"
                  : "创建账号"}
            </button>
          </form>
        )}
        <p className="mt-3 text-xs leading-relaxed text-ink-500">
          密码 PBKDF2 哈希；会话 30 天。登录后权益使用{" "}
          <code className="text-[10px]">user:&lt;id&gt;</code>{" "}
          作用域，并自动合并本机 device 权益与命盘。
        </p>
      </SectionCard>
    </div>
  );
}
