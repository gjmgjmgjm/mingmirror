import type { ReactNode } from "react";

interface ErrorPanelProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

function formatError(message: string): string {
  if (
    message.includes("502") ||
    message.includes("503") ||
    message.includes("Failed to fetch") ||
    message.includes("NetworkError")
  ) {
    return "后端服务未启动或暂时不可用，请检查 server 是否运行（python -m server.app --serve）。";
  }
  if (message.includes("400") || message.includes("422")) {
    return "请求参数有误，请检查输入格式。";
  }
  if (message.includes("404")) {
    return "请求的资源不存在。";
  }
  return message;
}

export default function ErrorPanel({
  title = "出错了",
  children,
  className = "",
}: ErrorPanelProps) {
  const text = typeof children === "string" ? formatError(children) : children;
  return (
    <div className={`error-panel ${className}`}>
      <p className="font-medium">{title}</p>
      <p className="text-sm">{text}</p>
    </div>
  );
}
