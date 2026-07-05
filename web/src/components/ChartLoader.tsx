import { useEffect, useMemo, useState } from "react";

const MESSAGES = [
  "正在排盘，定日主旺衰……",
  "读取十神关系，找用神忌神……",
  "分析五行生克，调候格局……",
  "检索相似案例，交叉验证……",
  "生成领域解读，润色断语……",
];

const GLYPHS = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥乾坤坎离震巽艮兑";
const FLOATING = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥";
const TIANGAN = "甲乙丙丁戊己庚辛壬癸".split("");
const DIZHI = "子丑寅卯辰巳午未申酉戌亥".split("");

function useScramble(text: string) {
  const [display, setDisplay] = useState(text);

  useEffect(() => {
    let frame = 0;
    const total = 18;
    setDisplay(
      text
        .split("")
        .map(() => GLYPHS[Math.floor(Math.random() * GLYPHS.length)])
        .join("")
    );
    const id = setInterval(() => {
      frame++;
      if (frame >= total) {
        setDisplay(text);
        clearInterval(id);
        return;
      }
      const ratio = frame / total;
      setDisplay(
        text
          .split("")
          .map((ch, i) => {
            if (ch === "，" || ch === "、" || ch === "……") return ch;
            if (i / text.length > ratio) {
              return GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
            }
            return ch;
          })
          .join("")
      );
    }, 45);
    return () => clearInterval(id);
  }, [text]);

  return display;
}

export default function ChartLoader() {
  const [messageIndex, setMessageIndex] = useState(0);
  const scrambled = useScramble(MESSAGES[messageIndex]);

  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((idx) => (idx + 1) % MESSAGES.length);
    }, 2800);
    return () => clearInterval(interval);
  }, []);

  const floaters = useMemo(() => {
    return Array.from({ length: 18 }, (_, i) => ({
      char: FLOATING[i % FLOATING.length],
      top: `${10 + Math.random() * 80}%`,
      left: `${5 + Math.random() * 90}%`,
      delay: `${Math.random() * 5}s`,
      duration: `${6 + Math.random() * 6}s`,
      size: 0.7 + Math.random() * 0.8,
    }));
  }, []);

  return (
    <div className="relative overflow-hidden rounded-3xl border border-ink-300/20 bg-gradient-to-br from-ink-900 via-ink-950 to-black p-10 shadow-2xl dark:border-ink-600/30 md:p-14">
      {/* Mesh aurora background */}
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute -left-1/4 -top-1/4 h-[150%] w-[150%] animate-aurora rounded-full bg-[radial-gradient(circle,rgba(201,54,29,0.18),transparent_60%)]" />
        <div className="absolute -bottom-1/4 -right-1/4 h-[150%] w-[150%] animate-aurora-reverse rounded-full bg-[radial-gradient(circle,rgba(201,162,39,0.14),transparent_60%)]" style={{ animationDelay: "-4s" }} />
      </div>

      {/* Floating background glyphs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {floaters.map((f, i) => (
          <span
            key={i}
            className="absolute animate-float-glyph font-serif text-ink-100/10 dark:text-ink-100/10"
            style={{
              top: f.top,
              left: f.left,
              fontSize: `${f.size}rem`,
              animationDelay: f.delay,
              animationDuration: f.duration,
            }}
          >
            {f.char}
          </span>
        ))}
      </div>

      {/* Center mandala stage */}
      <div className="relative mx-auto flex h-96 w-96 items-center justify-center md:h-[28rem] md:w-[28rem]">
        {/* Outer glow pulse rings */}
        <div className="absolute inset-0 rounded-full border border-vermilion/10 animate-pulse-ring-1" />
        <div className="absolute inset-4 rounded-full border border-gold/10 animate-pulse-ring-2" />

        {/* Outer dizhi ring */}
        <svg
          className="absolute h-full w-full animate-spin-slow text-vermilion/55"
          viewBox="0 0 200 200"
          aria-hidden="true"
        >
          <circle
            cx="100"
            cy="100"
            r="92"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            strokeDasharray="4 6"
          />
          <g transform="translate(100, 100)">
            {DIZHI.map((char, i) => {
              const deg = i * 30;
              return (
                <text
                  key={char}
                  x="0"
                  y="0"
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize="13"
                  fontWeight="bold"
                  fill="currentColor"
                  transform={`rotate(${deg}) translate(0,-82) rotate(${-deg})`}
                >
                  {char}
                </text>
              );
            })}
          </g>
        </svg>

        {/* Middle tiangan ring (reversed spin) */}
        <svg
          className="absolute h-60 w-60 animate-spin-reverse-slow text-gold/55 md:h-72 md:w-72"
          viewBox="0 0 200 200"
          aria-hidden="true"
        >
          <circle
            cx="100"
            cy="100"
            r="64"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            strokeDasharray="2 4"
          />
          <g transform="translate(100, 100)">
            {TIANGAN.map((char, i) => {
              const deg = i * 36;
              return (
                <text
                  key={char}
                  x="0"
                  y="0"
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize="13"
                  fontWeight="bold"
                  fill="currentColor"
                  transform={`rotate(${deg}) translate(0,-56) rotate(${-deg})`}
                >
                  {char}
                </text>
              );
            })}
          </g>
        </svg>

        {/* Orbiting energy beads */}
        <div className="absolute inset-0 animate-orbit-1" style={{ transformStyle: "preserve-3d" }}>
          <span
            className="absolute left-1/2 top-0 h-3 w-3 -translate-x-1/2 rounded-full bg-vermilion"
            style={{ boxShadow: "0 0 14px 2px rgba(201,54,29,0.7)" }}
          />
        </div>
        <div className="absolute inset-0 animate-orbit-2" style={{ transformStyle: "preserve-3d" }}>
          <span
            className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-gold"
            style={{ boxShadow: "0 0 12px 2px rgba(201,162,39,0.6)" }}
          />
        </div>
        <div className="absolute inset-0 animate-orbit-3" style={{ transformStyle: "preserve-3d" }}>
          <span
            className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 rounded-full bg-jade"
            style={{ boxShadow: "0 0 10px 2px rgba(60,179,113,0.6)" }}
          />
        </div>

        {/* Taiji */}
        <div className="relative h-28 w-28 animate-taiji md:h-32 md:w-32">
          <svg className="h-full w-full" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" className="text-ink-100/40" strokeWidth="1.5" />
            <path
              d="M50,2 A24,24 0 0,1 50,50 A24,24 0 0,0 50,98 A48,48 0 1,1 50,2 Z"
              fill="currentColor"
              className="text-ink-100"
            />
            <circle cx="50" cy="26" r="8" className="fill-ink-900" />
            <circle cx="50" cy="74" r="8" className="fill-ink-100" />
          </svg>
        </div>
      </div>

      {/* Text */}
      <div className="relative mt-8 text-center">
        <p className="bg-gradient-to-r from-vermilion via-gold to-vermilion bg-clip-text text-xl font-bold tracking-[0.3em] text-transparent md:text-2xl">
          八字分析中
        </p>
        <p className="mt-2 h-6 font-mono text-sm text-ink-200 md:text-base">
          {scrambled}
        </p>
      </div>

      <style>{`
        @keyframes spin-slow {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes spin-reverse-slow {
          from { transform: rotate(360deg); }
          to { transform: rotate(0deg); }
        }
        @keyframes taiji {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes breathe {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.92; }
        }
        @keyframes aurora {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(8%, 6%) scale(1.1); }
        }
        @keyframes aurora-reverse {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(-6%, -8%) scale(1.08); }
        }
        @keyframes float-glyph {
          0% { transform: translateY(0) rotate(0deg); opacity: 0; }
          20% { opacity: 0.6; }
          80% { opacity: 0.6; }
          100% { transform: translateY(-40px) rotate(20deg); opacity: 0; }
        }
        @keyframes pulse-ring-1 {
          0% { transform: scale(0.9); opacity: 0.6; }
          100% { transform: scale(1.15); opacity: 0; }
        }
        @keyframes pulse-ring-2 {
          0% { transform: scale(0.85); opacity: 0.5; }
          100% { transform: scale(1.25); opacity: 0; }
        }
        @keyframes orbit-1 {
          from { transform: rotate(0deg) rotateX(60deg); }
          to { transform: rotate(360deg) rotateX(60deg); }
        }
        @keyframes orbit-2 {
          from { transform: rotate(120deg) rotateX(50deg) rotateY(20deg); }
          to { transform: rotate(480deg) rotateX(50deg) rotateY(20deg); }
        }
        @keyframes orbit-3 {
          from { transform: rotate(240deg) rotateX(70deg) rotateY(-15deg); }
          to { transform: rotate(600deg) rotateX(70deg) rotateY(-15deg); }
        }

        .animate-spin-slow { animation: spin-slow 12s linear infinite; }
        .animate-spin-reverse-slow { animation: spin-reverse-slow 16s linear infinite; }
        .animate-taiji { animation: taiji 10s linear infinite; }
        .animate-aurora { animation: aurora 8s ease-in-out infinite; }
        .animate-aurora-reverse { animation: aurora-reverse 10s ease-in-out infinite; }
        .animate-float-glyph { animation: float-glyph 8s ease-in-out infinite; }
        .animate-pulse-ring-1 { animation: pulse-ring-1 2.4s ease-out infinite; }
        .animate-pulse-ring-2 { animation: pulse-ring-2 2.4s ease-out infinite 1.2s; }
        .animate-orbit-1 { animation: orbit-1 5s linear infinite; }
        .animate-orbit-2 { animation: orbit-2 7s linear infinite; }
        .animate-orbit-3 { animation: orbit-3 9s linear infinite; }
      `}</style>
    </div>
  );
}
