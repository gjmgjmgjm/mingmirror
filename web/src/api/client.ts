export const API_PREFIX = "/api/v1";

interface FetchOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, params?: FetchOptions["params"]): string {
  const url = new URL(path, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export async function fetchJson<T>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const { params, ...init } = options;
  const url = buildUrl(`${API_PREFIX}${path}`, params);
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    ...init,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "Unknown error");
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  return response.json() as Promise<T>;
}

export interface BaziBasicInfo {
  bazi: string;
  day_master: string;
  month_branch: string;
  pattern: string;
  useful_gods: string[];
  taboo_gods: string[];
}

export interface BaziDomainAnalysis {
  career: string;
  wealth: string;
  marriage: string;
  health: string;
}

export interface Milestone {
  year: number;
  age: number;
  type: string;
  description: string;
}

export interface BaziResult {
  basic_info: BaziBasicInfo;
  reasoning: string;
  domain_analysis: BaziDomainAnalysis;
  wealth_level?: string;
  wealth_evidence?: string;
  marriage_status?: string;
  marriage_evidence?: string;
  milestones?: Milestone[];
  personality?: string;
  events?: string[];
  summary: string[];
  confidence: "high" | "medium" | "low";
  caveats: string[];
  error?: string;
}

export interface BaziAnalyzeResponse {
  bazi: string;
  result: BaziResult;
}

export function analyzeBazi(
  bazi: string,
  question: string,
  topK?: number
): Promise<BaziAnalyzeResponse> {
  return fetchJson<BaziAnalyzeResponse>("/bazi/analyze", {
    method: "POST",
    body: JSON.stringify({ bazi, question, top_k: topK }),
  });
}

export interface BaziTimelineResponse {
  bazi: string;
  dayun: Array<{
    index: number;
    pillar: string;
    start_age: number;
    end_age: number;
    start_year: number | null;
    end_year: number | null;
  }>;
  liunian: Array<{ year: number; pillar: string; stem: string; branch: string }>;
}

export function fetchBaziTimeline(
  bazi: string,
  gender: string,
  birthDate: string,
  birthTime: string,
  calendarType: "solar" | "lunar" = "solar",
  untilAge = 80
): Promise<BaziTimelineResponse> {
  return fetchJson<BaziTimelineResponse>("/bazi/timeline", {
    method: "POST",
    body: JSON.stringify({
      bazi,
      gender,
      birth_date: birthDate,
      birth_time: birthTime,
      calendar_type: calendarType,
      until_age: untilAge,
    }),
  });
}

export interface BaziYearlyResponse {
  bazi: string;
  mode: string;
  result: Record<string, unknown>;
}

export function analyzeYearly(
  bazi: string,
  gender: string,
  birthDate: string,
  birthTime: string,
  calendarType: "solar" | "lunar" = "solar",
  mode: "10y" | "lifetime" = "10y"
): Promise<BaziYearlyResponse> {
  return fetchJson<BaziYearlyResponse>("/bazi/yearly", {
    method: "POST",
    body: JSON.stringify({
      bazi,
      gender,
      birth_date: birthDate,
      birth_time: birthTime,
      calendar_type: calendarType,
      mode,
    }),
  });
}

export interface QizhengBasicInfo {
  chart: string;
  day_master?: string;
  life_palace?: string;
  body_palace?: string;
  dominant_stars?: string[];
  twelve_palaces?: Record<string, string>;
}

export interface QizhengDomainAnalysis {
  career: string;
  wealth: string;
  marriage: string;
  health: string;
}

export interface QizhengResult {
  basic_info: QizhengBasicInfo;
  reasoning: string;
  domain_analysis: QizhengDomainAnalysis;
  summary?: string[];
  confidence?: "high" | "medium" | "low";
  caveats?: string[];
  error?: string;
}

export interface QizhengAnalyzeResponse {
  bazi: string;
  result: QizhengResult;
}

export function analyzeQizheng(
  bazi: string,
  question: string
): Promise<QizhengAnalyzeResponse> {
  return fetchJson<QizhengAnalyzeResponse>("/qizheng/analyze", {
    method: "POST",
    body: JSON.stringify({ bazi, question }),
  });
}

export interface QizhengYearlyResponse {
  bazi: string;
  mode: string;
  result: Record<string, unknown>;
}

export function analyzeQizhengYearly(
  bazi: string,
  gender: string,
  birthYear: number,
  mode: "10y" | "lifetime" = "10y"
): Promise<QizhengYearlyResponse> {
  return fetchJson<QizhengYearlyResponse>("/qizheng/yearly", {
    method: "POST",
    body: JSON.stringify({ bazi, gender, birth_year: birthYear, mode }),
  });
}

export interface BaziFromDatetimeResponse {
  bazi: string;
  pillars: Record<string, string>;
  calendar_type: string;
}

export function baziFromDatetime(
  birthDatetime: string,
  calendarType: "solar" | "lunar" = "solar"
): Promise<BaziFromDatetimeResponse> {
  return fetchJson<BaziFromDatetimeResponse>("/bazi/from_datetime", {
    method: "POST",
    body: JSON.stringify({
      birth_datetime: birthDatetime,
      calendar_type: calendarType,
    }),
  });
}

export interface DestinySystemsResponse {
  available: string[];
  all: string[];
}

export function fetchDestinySystems(): Promise<DestinySystemsResponse> {
  return fetchJson<DestinySystemsResponse>("/destiny/systems");
}

export interface DomainConclusion {
  domain: string;
  text: string;
  confidence: string;
}

export interface SystemResult {
  system: string;
  chart_info: {
    bazi: string;
    question?: string;
    gender?: string;
    birth_datetime?: string;
  };
  raw_result: Record<string, unknown>;
  domain_conclusions: DomainConclusion[];
}

export interface AlignedEntry {
  consensus: string;
  confidence: "high" | "medium" | "low";
  dissent?: string[];
}

export interface DestinyAnalyzeResponse {
  bazi: string;
  question: string;
  per_system: SystemResult[];
  aligned: Record<string, AlignedEntry>;
  final_summary: string;
  overall_confidence: "high" | "medium" | "low";
  strategy?: string;
}

export interface LocationPayload {
  longitude: number;
  latitude: number;
  timezone: string;
}

export interface DestinyAnalyzeRequest {
  bazi: string;
  question?: string;
  systems: string[];
  strategy?: string;
  gender?: string;
  birth_datetime?: string;
  location?: LocationPayload;
}

export function analyzeDestiny(
  payload: DestinyAnalyzeRequest
): Promise<DestinyAnalyzeResponse> {
  return fetchJson<DestinyAnalyzeResponse>("/destiny/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function councilDestiny(
  payload: DestinyAnalyzeRequest
): Promise<DestinyAnalyzeResponse> {
  return fetchJson<DestinyAnalyzeResponse>("/destiny/council", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface DailyFortuneRequest {
  bazi: string;
  date?: string;
}

export interface DailyFortuneResponse {
  date: string;
  today_pillars: Record<string, string>;
  user_day_master: string;
  user_day_master_element: string;
  weather: string;
  weather_label: string;
  description: string;
  energy: Record<string, number>;
  dos: string[];
  avoids: string[];
  error?: string;
}

export function fetchDailyFortune(
  payload: DailyFortuneRequest
): Promise<DailyFortuneResponse> {
  return fetchJson<DailyFortuneResponse>("/destiny/daily", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface DestinyScriptTalent {
  name: string;
  description: string;
}

export interface DestinyScriptWeakness {
  name: string;
  description: string;
}

export interface DestinyScriptCharacterCard {
  day_master: string;
  pattern: string;
  strength: string;
  talents: DestinyScriptTalent[];
  weaknesses: DestinyScriptWeakness[];
  current_chapter: string;
  next_chapter_preview: string;
}

export interface DestinyScriptChapter {
  index: number;
  pillar: string;
  age_range: string;
  year_range: string;
  theme: string;
  challenge: string;
  opportunity: string;
  advice: string;
  key_events: string[];
}

export interface DestinyScriptResponse {
  character_card: DestinyScriptCharacterCard;
  chapters: DestinyScriptChapter[];
  opening: string;
  closing: string;
}

export interface DestinyScriptRequest {
  bazi: string;
  gender?: string;
  birth_datetime?: string;
  birth_year?: number;
}

export function fetchDestinyScript(
  payload: DestinyScriptRequest
): Promise<DestinyScriptResponse> {
  return fetchJson<DestinyScriptResponse>("/destiny/script", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
