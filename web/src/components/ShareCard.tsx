import { useRef, useState } from "react";
import { Share2, Download } from "lucide-react";
import { toPng } from "html-to-image";
import { SealStamp } from "./ui";
import { track } from "../lib/analytics";

interface ShareCardProps {
  bazi: string;
  /** 日主天干,如 "庚" */
  dayMaster?: string;
  /** 一句话钩子(日主取象 / 命书总结) */
  headline?: string;
  /** 男命 / 女命 */
  genderLabel?: string;
  /** 按钮文案 */
  label?: string;
  className?: string;
}

/**
 * 分享命盘海报:html-to-image 把样式卡转 PNG(抖音/小红书方图友好),
 * 优先 navigator.share(移动端原生分享),否则触发下载。
 * 海报节点离屏渲染(不可见但保留布局,供 html-to-image 取图)。
 */
export default function ShareCard({
  bazi,
  dayMaster,
  headline,
  genderLabel,
  label = "分享命盘",
  className,
}: ShareCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  const handleShare = async () => {
    if (!cardRef.current || busy) return;
    setBusy(true);
    setHint(null);
    try {
      const dataUrl = await toPng(cardRef.current, {
        pixelRatio: 2,
        cacheBust: true,
        backgroundColor: "#f4f1ea",
      });
      // 尝试 Web Share(支持图片的移动端)
      let shared = false;
      try {
        if (navigator.canShare) {
          const blob = await (await fetch(dataUrl)).blob();
          const file = new File([blob], "mingmirror.png", { type: "image/png" });
          if (navigator.canShare({ files: [file] })) {
            await navigator.share({ files: [file], title: "命镜 · 我的命盘" });
            shared = true;
            track("landing_share", { medium: "web_share" });
          }
        }
      } catch {
        // 用户取消或不可用 → 走下载
      }
      if (!shared) {
        const a = document.createElement("a");
        a.href = dataUrl;
        a.download = `命镜-${bazi.replace(/\s+/g, "")}.png`;
        a.click();
        setHint("海报已生成,长按或右键保存分享。");
        track("landing_share", { medium: "save" });
      }
    } catch {
      // 降级:复制命盘文本
      try {
        await navigator.clipboard?.writeText(`命镜 · ${genderLabel || ""} ${bazi}\n${headline || ""}`);
        setHint("图片生成失败,已复制命盘文本。");
        track("landing_share", { medium: "copy_fallback" });
      } catch {
        setHint("分享失败,请稍后重试。");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={handleShare}
        disabled={busy}
        className={`inline-flex items-center gap-1.5 rounded-lg bg-jade/15 px-3 py-1.5 text-xs font-medium text-jade transition hover:bg-jade/25 disabled:opacity-50 ${className || ""}`}
      >
        {busy ? <Download className="h-3.5 w-3.5 animate-pulse" /> : <Share2 className="h-3.5 w-3.5" />}
        {busy ? "生成中…" : label}
      </button>
      {hint && <span className="ml-2 text-[11px] text-ink-400">{hint}</span>}

      {/* 离屏海报节点(1080×1080 方图,抖音/小红书友好) */}
      <div
        aria-hidden="true"
        style={{ position: "fixed", left: "-99999px", top: 0, pointerEvents: "none" }}
      >
        <div
          ref={cardRef}
          style={{
            width: 1080,
            height: 1080,
            padding: 80,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "space-between",
            fontFamily: "'Noto Serif SC','Songti SC','SimSun',serif",
            color: "#2c2824",
            background:
              "radial-gradient(circle at 80% 15%, rgba(201,162,39,0.16), transparent 55%), radial-gradient(circle at 18% 88%, rgba(197,61,47,0.12), transparent 55%), linear-gradient(135deg,#f4f1ea 0%,#e8e3d8 100%)",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
            <div
              style={{
                width: 150, height: 150, border: "6px solid #c53d2f", borderRadius: 22,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 86, color: "#c53d2f", letterSpacing: 8,
                fontFamily: "'Zhi Mang Xing','Noto Serif SC','Songti SC',serif",
                background: "rgba(255,255,255,0.5)",
              }}
            >
              命镜
            </div>
            <div style={{ fontSize: 30, letterSpacing: 6, color: "#a89e8a" }}>MingMirror · 命运数字孪生</div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 28 }}>
            {genderLabel && (
              <div style={{ fontSize: 34, color: "#7a746a", letterSpacing: 4 }}>{genderLabel}</div>
            )}
            <div
              style={{
                fontSize: 96, fontWeight: 700, letterSpacing: 12, color: "#2c2824",
                fontFamily: "'Noto Serif SC','Songti SC',serif",
              }}
            >
              {bazi}
            </div>
            {dayMaster && (
              <div style={{ fontSize: 40, color: "#c9a227", letterSpacing: 3 }}>
                {dayMaster}日主
              </div>
            )}
            {headline && (
              <div style={{ fontSize: 36, color: "#4a453d", maxWidth: 880, textAlign: "center", lineHeight: 1.5 }}>
                {headline}
              </div>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
            <div style={{ fontSize: 28, color: "#5a8f7b", letterSpacing: 4 }}>
              可计算 · 可验证 · 可交互
            </div>
            <div style={{ fontSize: 24, color: "#a89e8a", letterSpacing: 2 }}>
              在线免费读命书 · 生成你的命运数字孪生
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
