import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader, SectionCard, ErrorPanel } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";

export default function Account() {
  const { user, loading, login, register, logout, changePassword } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
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
      } else {
        await register(email.trim(), password, displayName.trim());
        setMsg("注册成功");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
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
      <SectionCard title={mode === "login" ? "登录" : "注册"}>
        <div className="mb-3 flex gap-2 text-sm">
          <button
            type="button"
            className={`rounded-full px-3 py-1 ${
              mode === "login"
                ? "bg-vermilion/15 text-vermilion"
                : "text-ink-500"
            }`}
            onClick={() => setMode("login")}
          >
            登录
          </button>
          <button
            type="button"
            className={`rounded-full px-3 py-1 ${
              mode === "register"
                ? "bg-vermilion/15 text-vermilion"
                : "text-ink-500"
            }`}
            onClick={() => setMode("register")}
          >
            注册
          </button>
        </div>
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
            {busy ? "请稍候…" : mode === "login" ? "登录" : "创建账号"}
          </button>
        </form>
        <p className="mt-3 text-xs leading-relaxed text-ink-500">
          密码使用 PBKDF2 本地哈希存储；会话令牌 30 天有效。匿名
          device_id 在登录时自动关联并合并套餐权益。
        </p>
      </SectionCard>
    </div>
  );
}
