export const API_PREFIX = "/api/v1";

// ---------------------------------------------------------------------------
// Chart identity (product layer)
// ---------------------------------------------------------------------------

export interface ServerChart {
  id: string;
  bazi: string;
  gender: string;
  birth_date: string;
  birth_time: string;
  calendar_type: string;
  location?: {
    name?: string;
    longitude: number;
    latitude: number;
    timezone: string;
  } | null;
  label: string;
  created_at: number;
  updated_at: number;
}

export interface CreateChartRequest {
  bazi: string;
  gender?: string;
  birth_date?: string;
  birth_time?: string;
  calendar_type?: string;
  location?: {
    name?: string;
    longitude: number;
    latitude: number;
    timezone: string;
  };
  label?: string;
  device_id?: string;
  reuse_existing?: boolean;
}

export function createChart(payload: CreateChartRequest): Promise<ServerChart> {
  return fetchJson<ServerChart>("/charts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listCharts(
  limit = 50,
  deviceId?: string
): Promise<ServerChart[]> {
  return fetchJson<ServerChart[]>("/charts", {
    params: {
      limit,
      device_id: deviceId || undefined,
    },
  });
}

export interface DemoChart {
  id: string;
  label: string;
  blurb: string;
  bazi: string;
  gender: string;
  birth_date: string;
  birth_time: string;
  calendar_type: string;
  location?: {
    name?: string;
    longitude: number;
    latitude: number;
    timezone: string;
  };
  tags?: string[];
  highlights?: string[];
}

export function fetchDemoCharts(): Promise<{
  count: number;
  items: DemoChart[];
  note?: string;
  pricing_demo_code?: string;
}> {
  return fetchJson("/product/demo-charts");
}

export function fetchDemoChartPackage(
  demoId: string,
  opts?: PackageExportOptions
): Promise<ProductPackage> {
  return fetchJson(`/product/demo-charts/${encodeURIComponent(demoId)}/package`, {
    method: "POST",
    body: JSON.stringify({
      liunian_start_year: opts?.liunian_start_year,
      liunian_years: opts?.liunian_years ?? 10,
    }),
  });
}


export function getChart(
  chartId: string,
  deviceId?: string
): Promise<ServerChart> {
  return fetchJson<ServerChart>(`/charts/${encodeURIComponent(chartId)}`, {
    params: deviceId ? { device_id: deviceId } : undefined,
  });
}

export interface ProductPackage {
  meta: {
    bazi: string;
    gender: string;
    chart_id?: string | null;
    label: string;
    package_version: string;
  };
  report: Record<string, unknown>;
  auspicious: {
    event_label?: string;
    top?: Array<{
      date: string;
      day_pillar: string;
      score: number;
      reasoning: string;
    }>;
  };
  markdown: string;
  html: string;
  filename_stem: string;
  disclaimer: string;
}

export interface PackageExportOptions {
  liunian_start_year?: number;
  liunian_years?: number;
}

export function exportChartPackage(
  chartId: string,
  opts?: PackageExportOptions,
  deviceId?: string
): Promise<ProductPackage> {
  return fetchJson<ProductPackage>(
    `/charts/${encodeURIComponent(chartId)}/export/package`,
    {
      method: "POST",
      params: deviceId ? { device_id: deviceId } : undefined,
      body: JSON.stringify({
        liunian_start_year: opts?.liunian_start_year,
        liunian_years: opts?.liunian_years ?? 10,
      }),
    }
  );
}

export function exportBaziPackage(
  payload: CreateChartRequest & PackageExportOptions,
  deviceId?: string
): Promise<ProductPackage> {
  return fetchJson<ProductPackage>("/bazi/export/package", {
    method: "POST",
    params: deviceId ? { device_id: deviceId } : undefined,
    body: JSON.stringify(payload),
  });
}

export function downloadTextFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function openHtmlPrint(html: string) {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.open();
  w.document.write(html);
  w.document.close();
}

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
  // Lazy import to avoid circular deps with auth helpers
  let authHdrs: Record<string, string> = {};
  try {
    const { authHeaders } = await import("../lib/auth");
    authHdrs = authHeaders();
  } catch {
    authHdrs = {};
  }
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...authHdrs,
      ...(init.headers as Record<string, string> | undefined),
    },
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "Unknown error");
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  return response.json() as Promise<T>;
}

export interface AuthUserDto {
  id: string;
  email: string;
  display_name: string;
  created_at?: number;
  updated_at?: number;
  is_active?: boolean;
  email_verified?: boolean;
}

export interface AuthSessionResponse {
  user: AuthUserDto;
  token: string;
  expires_at: number;
  token_type: string;
  email_verify_token?: string;
  email_verify_hint?: string;
}

export function registerAccount(payload: {
  email: string;
  password: string;
  display_name?: string;
  device_id?: string;
}): Promise<AuthSessionResponse> {
  return fetchJson<AuthSessionResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loginAccount(payload: {
  email: string;
  password: string;
  device_id?: string;
}): Promise<AuthSessionResponse> {
  return fetchJson<AuthSessionResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logoutAccount(): Promise<{ ok: boolean; logged_out?: boolean }> {
  return fetchJson("/auth/logout", { method: "POST" });
}

export function fetchAuthMe(): Promise<{
  user: AuthUserDto;
  devices: string[];
}> {
  return fetchJson("/auth/me");
}

export function linkAuthDevice(device_id: string): Promise<{
  ok: boolean;
  devices: string[];
}> {
  return fetchJson("/auth/link-device", {
    method: "POST",
    body: JSON.stringify({ device_id }),
  });
}

export function changeAuthPassword(payload: {
  old_password: string;
  new_password: string;
}): Promise<AuthSessionResponse & { ok: boolean; message?: string }> {
  return fetchJson("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function requestEmailVerify(): Promise<{
  ok: boolean;
  email_verify_token?: string;
  email_verify_hint?: string;
}> {
  return fetchJson("/auth/request-verify", { method: "POST" });
}

export function verifyEmailToken(token: string): Promise<{
  ok: boolean;
  user: AuthUserDto;
}> {
  return fetchJson("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export function forgotPassword(email: string): Promise<{
  ok: boolean;
  message?: string;
  reset_token?: string;
  reset_hint?: string;
}> {
  return fetchJson("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function resetPassword(payload: {
  token: string;
  new_password: string;
}): Promise<AuthSessionResponse & { ok: boolean }> {
  return fetchJson("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function exportAccountData(): Promise<{
  ok: boolean;
  data: Record<string, unknown>;
}> {
  return fetchJson("/auth/export-data");
}

export function deleteAccount(payload: {
  password?: string;
  confirm?: string;
}): Promise<{ ok: boolean; deleted?: boolean; user_id?: string }> {
  return fetchJson("/auth/delete-account", {
    method: "POST",
    body: JSON.stringify({
      password: payload.password || "",
      confirm: payload.confirm || "DELETE",
    }),
  });
}

export function fetchOAuthAuthorize(
  provider: string,
  state?: string
): Promise<{
  ok: boolean;
  provider: string;
  authorize_url: string;
  state: string;
  ready: boolean;
  redirect_uri?: string;
  hint?: string | null;
}> {
  const q = state ? `?state=${encodeURIComponent(state)}` : "";
  return fetchJson(`/auth/oauth/${encodeURIComponent(provider)}${q}`);
}

export function exchangeOAuthCode(
  provider: string,
  payload: { code: string; state?: string; device_id?: string }
): Promise<AuthSessionResponse & { ok?: boolean; provider?: string }> {
  return fetchJson(`/auth/oauth/${encodeURIComponent(provider)}/exchange`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchMyCharts(limit = 50): Promise<{
  user_id: string;
  count: number;
  items: Array<{
    id: string;
    bazi: string;
    label?: string;
    gender?: string;
    birth_date?: string;
    birth_time?: string;
    user_id?: string;
    device_id?: string;
  }>;
}> {
  return fetchJson(`/me/charts`, { params: { limit } });
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

export interface BaziQuxiang {
  day_master?: string;
  key_shishen?: string;
  career?: string;
  health?: string;
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
  // 结构层专字段(engine 注入,确定性)
  quxiang?: BaziQuxiang;
  liuqin_strength?: Record<string, string>; // father/mother/spouse/son/daughter/brother/sister → "强"|"弱"
  liuqin_analysis?: string;
  dayun_summary?: string;
  /** 应期展示决策 hard_shortlist | soft_hint | trend_only | unavailable */
  year_timing_surface?: YearTimingSurface;
  /** 六亲细断 det：性格/能力/健康/关系/大运应期 */
  liuqin_dossier?: LiuqinDossier;
  error?: string;
}

export interface LiuqinTimingHighlight {
  pillar?: string;
  ages?: string;
  note?: string;
  stem_shishen?: string;
}

export interface LiuqinLiunianSample {
  year?: number;
  pillar?: string;
  age?: number;
  stem_shishen?: string;
  note?: string;
  kind?: string;
}

export interface LiuqinPalaceNote {
  palace_label?: string;
  palace_branch?: string;
  palace_main_qi?: string;
  palace_note?: string;
}

export interface LiuqinMemberDossier {
  key?: string;
  label?: string;
  star?: string;
  /** Dual-star list e.g. ["正印","偏印"] */
  stars?: string[];
  exists?: boolean;
  strength?: string;
  support_text?: string;
  locations_text?: string;
  dual_star_note?: string;
  palace?: LiuqinPalaceNote;
  character?: string;
  ability?: string;
  health?: string;
  appearance?: string;
  relation?: string;
  timing?: {
    dayun_highlights?: LiuqinTimingHighlight[];
    favorable_hint?: string;
    caution_hint?: string;
    /** Symbolic year samples only — never assert single year */
    liunian_samples?: LiuqinLiunianSample[];
  };
  narrative?: string;
  honesty?: string;
}

export interface LiuqinDossier {
  gender?: string;
  day_master?: string;
  members?: Partial<Record<
    "father" | "mother" | "spouse" | "son" | "daughter" | "brother" | "sister",
    LiuqinMemberDossier
  >>;
  children_bias?: string;
  spouse_palace?: Record<string, unknown>;
  parents_palace?: Record<string, unknown>;
  children_palace?: Record<string, unknown>;
  disclaimer?: string;
}

export interface YearTimingCandidate {
  year: number;
  gan_zhi: string;
  score: number;
  confidence: string;
  reasons: string[];
  option_letter?: string;
  option_text?: string;
  /** True when year also appears in liuqin symbolic samples */
  liuqin_overlap?: boolean;
  /** Soft structural critic preference — never means「必在此年」 */
  critic_prefer?: boolean;
}

export interface StructuralCriticMeta {
  letter?: string;
  reason?: string;
  picked_score?: number;
  base_top1?: string;
  assert_single_year?: boolean;
  prefer_year?: number;
  prefer_letter?: string;
}

export interface LiuqinYearBridgeSample {
  member_key?: string;
  member_label?: string;
  year?: number;
  pillar?: string;
  age?: number;
  note?: string;
  kind?: string;
}

export interface LiuqinYearBridge {
  member_keys?: string[];
  samples?: LiuqinYearBridgeSample[];
  overlap_years?: number[];
  honesty?: string;
}

export interface YearTimingSurface {
  event_kind?: string | null;
  display_mode:
    | "hard_shortlist"
    | "soft_hint"
    | "trend_only"
    | "unavailable"
    | string;
  trust: string;
  assert_single_year: boolean;
  candidates: YearTimingCandidate[];
  product_title?: string;
  product_copy?: string;
  disclaimer?: string;
  meta?: Record<string, unknown> & {
    liuqin_bridge?: LiuqinYearBridge;
    structural_critic?: StructuralCriticMeta;
  };
}

export interface BaziAnalyzeResponse {
  bazi: string;
  result: BaziResult;
}

export interface AnalyzeBaziOptions {
  gender?: string;
  birthDate?: string;
  birthTime?: string;
  calendarType?: "solar" | "lunar";
  topK?: number;
}

export function analyzeBazi(
  bazi: string,
  question: string,
  options?: AnalyzeBaziOptions | number
): Promise<BaziAnalyzeResponse> {
  // Backward compatible: third arg may still be topK number.
  const opts: AnalyzeBaziOptions =
    typeof options === "number" ? { topK: options } : options || {};
  return fetchJson<BaziAnalyzeResponse>("/bazi/analyze", {
    method: "POST",
    body: JSON.stringify({
      bazi,
      question,
      top_k: opts.topK,
      gender: opts.gender || "male",
      birth_date: opts.birthDate || "",
      birth_time: opts.birthTime || "00:00",
      calendar_type: opts.calendarType || "solar",
    }),
  });
}

/** Zero-LLM year shortlist / trend surface (product honesty layer). */
export function fetchYearTiming(
  bazi: string,
  question: string,
  options: {
    optionTexts?: string[];
    gender?: string;
    birthDate?: string;
    birthTime?: string;
  } = {}
): Promise<{ bazi: string; year_timing_surface: YearTimingSurface }> {
  return fetchJson("/bazi/year-timing", {
    method: "POST",
    body: JSON.stringify({
      bazi,
      question,
      options: options.optionTexts || [],
      gender: options.gender || "male",
      birth_date: options.birthDate || "",
      birth_time: options.birthTime || "00:00",
    }),
  });
}

export interface ReportMeta {
  bazi: string;
  gender: string;
  gender_label: string;
}

export interface ReportSection {
  id: string;
  title: string;
  trust: "certain" | "ai";
  data: Record<string, any>;
}

export interface ReportData {
  meta: ReportMeta;
  sections: ReportSection[];
}

export interface BaziReportResponse {
  bazi: string;
  report: ReportData;
}

export function fetchBaziReport(
  bazi: string,
  gender: string,
  birthDate: string,
  birthTime: string,
  calendarType: "solar" | "lunar" = "solar",
  topK = 3
): Promise<BaziReportResponse> {
  return fetchJson<BaziReportResponse>("/bazi/report", {
    method: "POST",
    body: JSON.stringify({
      bazi,
      gender,
      birth_date: birthDate,
      birth_time: birthTime,
      calendar_type: calendarType,
      top_k: topK,
    }),
  });
}

export interface AuspiciousHour {
  branch: string;
  pillar: string;
  label: string;
  clock: string;
  start_hour: number;
  end_hour: number;
  score: number;
  reasoning: string;
  recommended: boolean;
}

export interface AuspiciousDay {
  date: string;
  day_pillar: string;
  score: number;
  weather: string;
  shishen: string;
  shensha?: { name: string; category?: string; effect: "吉" | "凶"; info?: string }[];
  reasoning: string;
  dos: string[];
  avoids: string[];
  hours?: AuspiciousHour[];
  best_hour?: AuspiciousHour | null;
  recommended: boolean;
}

export interface AuspiciousResponse {
  bazi: string;
  gender?: string;
  event_type: string;
  event_label: string;
  useful_gods: string[];
  taboo_gods: string[];
  date_from?: string;
  date_to?: string;
  days: AuspiciousDay[];
  top?: AuspiciousDay[];
  ics?: string;
  error?: string;
}

export function fetchBaziAuspicious(
  bazi: string,
  gender: string,
  eventType: string,
  dateFrom: string,
  dateTo: string,
  topN = 12,
  options?: { includeIcs?: boolean; hourTopK?: number }
): Promise<AuspiciousResponse> {
  return fetchJson<AuspiciousResponse>("/bazi/auspicious", {
    method: "POST",
    body: JSON.stringify({
      bazi,
      gender,
      event_type: eventType,
      date_from: dateFrom,
      date_to: dateTo,
      top_n: topN,
      hour_top_k: options?.hourTopK ?? 3,
      include_ics: options?.includeIcs ?? false,
    }),
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
  mode: "10y" | "20y" | "lifetime" = "10y",
  opts?: { start_year?: number; years?: number }
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
      start_year: opts?.start_year,
      years: opts?.years,
    }),
  });
}

export interface QizhengBasicInfo {
  chart: string;
  day_master?: string;
  life_palace?: string;
  body_palace?: string;
  body_lord?: string;
  five_element_pattern?: string;
  nayin?: string;
  dominant_stars?: string[];
  twelve_palaces?: Record<string, string>;
  trust?: string;
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
  question: string,
  dignityTable: "default" | "yang" = "default"
): Promise<QizhengAnalyzeResponse> {
  return fetchJson<QizhengAnalyzeResponse>("/qizheng/analyze", {
    method: "POST",
    body: JSON.stringify({ bazi, question, dignity_table: dignityTable }),
  });
}

export interface QizhengYearlyDayun {
  pillar: string;
  palace?: string;
  start_age: number;
  end_age: number;
  theme: string;
  focus: string;
}

export interface QizhengYearlyStar {
  name: string;
  strength?: string;
  dignity?: string;
  rulership?: string;
}

export interface QizhengYearlyItem {
  year: number;
  pillar: string;
  overview: string;
  career: string;
  wealth: string;
  marriage: string;
  health: string;
  caution: string;
  active_palace?: string;
  palace_lord?: string;
  palace_lord_relation?: string;
  stars_in_palace?: QizhengYearlyStar[];
  strongest_star?: QizhengYearlyStar;
  star_impact?: string;
  taishui_impact?: string;
  four_remainder_note?: string;
  pattern_note?: string;
}

export interface QizhengStructuralSummary {
  chart?: string;
  day_master?: string;
  life_palace?: string;
  body_palace?: string;
  body_lord?: string;
  five_element_pattern?: string;
  hour_branch?: string;
  patterns?: string[];
  dayun_count?: number;
  liunian_count?: number;
}

export interface QizhengYearlyResult {
  dayun_summary?: QizhengYearlyDayun[];
  yearly_analysis?: QizhengYearlyItem[];
  overall_guidance?: string;
  confidence?: "high" | "medium" | "low";
  trust?: string;
  note?: string;
  structural_summary?: QizhengStructuralSummary;
  caveats?: string[];
  error?: string;
  _rule_based?: boolean;
}

export interface QizhengYearlyResponse {
  bazi: string;
  mode: string;
  result: QizhengYearlyResult;
}

export function analyzeQizhengYearly(
  bazi: string,
  gender: string,
  birthYear: number,
  mode: "10y" | "lifetime" = "10y",
  dignityTable: "default" | "yang" = "default"
): Promise<QizhengYearlyResponse> {
  return fetchJson<QizhengYearlyResponse>("/qizheng/yearly", {
    method: "POST",
    body: JSON.stringify({
      bazi,
      gender,
      birth_year: birthYear,
      mode,
      dignity_table: dignityTable,
    }),
  });
}

// ---------------------------------------------------------------------------
// Zi Wei Dou Shu
// ---------------------------------------------------------------------------

export interface ZiweiPalace {
  name: string;
  branch: string;
  stars: string[];
  main_stars?: string[];
  aux_stars?: string[];
  sha_stars?: string[];
  star_traits?: string[];
}

export interface ZiweiMajorLimit {
  index: number;
  branch: string;
  palace_name: string;
  start_age: number;
  end_age: number;
  label: string;
  direction: string;
}

export interface ZiweiBasicInfo {
  ming_gong?: string;
  shen_gong?: string;
  zhu_xing?: string[];
  ming_aux?: string[];
  ming_sha?: string[];
  si_hua?: string[];
  bureau_label?: string;
  life_palace?: string;
  body_palace?: string;
  palaces?: ZiweiPalace[];
  major_limits?: ZiweiMajorLimit[];
  current_limit?: ZiweiMajorLimit | null;
  limit_direction?: string;
  trust?: string;
  note?: string;
}

export interface ZiweiResult {
  system?: string;
  basic_info?: ZiweiBasicInfo;
  structural?: {
    palaces?: ZiweiPalace[];
    bureau_label?: string;
    life_palace?: string;
    body_palace?: string;
  };
  domain_analysis?: Record<
    string,
    string | { text?: string; score?: number; keywords?: string[] }
  >;
  reasoning?: string;
  summary?: string[];
  confidence?: string;
  caveats?: string[];
}

export interface ZiweiAnalyzeResponse {
  bazi: string;
  result: ZiweiResult;
}

export function analyzeZiwei(payload: {
  bazi: string;
  gender?: string;
  question?: string;
  birth_datetime?: string;
  birth_date?: string;
  location?: { longitude: number; latitude: number; timezone: string };
}): Promise<ZiweiAnalyzeResponse> {
  return fetchJson<ZiweiAnalyzeResponse>("/ziwei/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface ZiweiLiunianYear {
  year: number;
  pillar: string;
  age?: number | null;
  palace_name: string;
  palace_branch: string;
  main_stars: string[];
  aux_stars: string[];
  sha_stars: string[];
  si_hua: string[];
  overview: string;
  focus: string;
  career: string;
  wealth: string;
  marriage: string;
  health: string;
  caution: string;
  major_limit?: ZiweiMajorLimit | null;
}

export interface ZiweiYearlyResult {
  error?: string | null;
  basic_info?: ZiweiBasicInfo;
  liunian?: ZiweiLiunianYear[];
  start_year?: number;
  end_year?: number;
  note?: string;
  trust?: string;
}

export function analyzeZiweiYearly(payload: {
  bazi: string;
  gender?: string;
  birth_date?: string;
  start_year?: number;
  end_year?: number;
  years?: number;
}): Promise<{ bazi: string; result: ZiweiYearlyResult }> {
  return fetchJson<{ bazi: string; result: ZiweiYearlyResult }>("/ziwei/yearly", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface BaziFromDatetimeResponse {
  bazi: string;
  pillars: Record<string, string>;
  calendar_type: string;
  is_leap_month?: boolean;
  true_solar_adjusted?: boolean;
  effective_datetime?: string;
}

export interface BaziFromDatetimeOptions {
  calendarType?: "solar" | "lunar";
  /** 农历闰月（仅 lunar 有效） */
  isLeapMonth?: boolean;
  /** 出生地经度；公历时用于真太阳时修正（东经为正） */
  longitude?: number;
}

export function baziFromDatetime(
  birthDatetime: string,
  calendarTypeOrOptions: "solar" | "lunar" | BaziFromDatetimeOptions = "solar"
): Promise<BaziFromDatetimeResponse> {
  const opts: BaziFromDatetimeOptions =
    typeof calendarTypeOrOptions === "string"
      ? { calendarType: calendarTypeOrOptions }
      : calendarTypeOrOptions || {};
  return fetchJson<BaziFromDatetimeResponse>("/bazi/from_datetime", {
    method: "POST",
    body: JSON.stringify({
      birth_datetime: birthDatetime,
      calendar_type: opts.calendarType || "solar",
      is_leap_month: Boolean(opts.isLeapMonth),
      longitude:
        typeof opts.longitude === "number" && Number.isFinite(opts.longitude)
          ? opts.longitude
          : undefined,
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
  system_weights?: Record<string, number>;
  weights_source?: string;
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
  /** Server chart UUID — used for calibration weight lookup. */
  chart_id?: string;
  use_calibration_weights?: boolean;
  system_weights?: Record<string, number>;
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

export interface BaziCase {
  bazi: string;
  analysis_corrected?: string;
  question?: string;
  tags?: string[];
}

export interface BaziCasesResponse {
  cases: BaziCase[];
}

export function listBaziCases(): Promise<BaziCasesResponse> {
  return fetchJson<BaziCasesResponse>("/bazi/cases");
}

export function submitFeedback(
  bazi: string,
  correct: boolean,
  note?: string
): Promise<{ status: string }> {
  return fetchJson<{ status: string }>("/bazi/feedback", {
    method: "POST",
    body: JSON.stringify({ bazi, correct, note }),
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

export interface LifeEvent {
  id: string;
  chart_id: string;
  event_type: string;
  happened_at: string;
  description: string;
}

export type EventType =
  | "study"
  | "job"
  | "job_change"
  | "startup"
  | "marriage"
  | "breakup"
  | "house"
  | "illness"
  | "surgery"
  | "award"
  | "move"
  | "other";

export interface CreateEventRequest {
  event_type: EventType;
  happened_at: string;
  description: string;
}

export function listEvents(
  chartId: string,
  deviceId?: string
): Promise<LifeEvent[]> {
  return fetchJson<LifeEvent[]>(`/charts/${encodeURIComponent(chartId)}/events`, {
    params: deviceId ? { device_id: deviceId } : undefined,
  });
}

export function createEvent(
  chartId: string,
  payload: CreateEventRequest,
  deviceId?: string
): Promise<LifeEvent> {
  return fetchJson<LifeEvent>(`/charts/${encodeURIComponent(chartId)}/events`, {
    method: "POST",
    params: deviceId ? { device_id: deviceId } : undefined,
    body: JSON.stringify(payload),
  });
}

export function deleteEvent(
  chartId: string,
  eventId: string,
  deviceId?: string
): Promise<{ deleted: boolean }> {
  return fetchJson<{ deleted: boolean }>(
    `/charts/${encodeURIComponent(chartId)}/events/${encodeURIComponent(eventId)}`,
    {
      method: "DELETE",
      params: deviceId ? { device_id: deviceId } : undefined,
    }
  );
}

export interface CalibrationEventDetail {
  event_id: string;
  event_type: string;
  happened_at: string;
  domain: string;
  scores: Record<string, number>;
  snippets: Record<string, string>;
}

export interface CalibrationResponse {
  chart_id: string;
  event_count: number;
  average_score: number;
  system_scores: Record<string, number>;
  adjusted_weights: Record<string, number>;
  suggested_hour_offset?: number;
  events: CalibrationEventDetail[];
  calibration_id?: string;
  created_at?: number;
}

export function calibrateChart(
  chartId: string,
  deviceId?: string
): Promise<CalibrationResponse> {
  return fetchJson<CalibrationResponse>(
    `/charts/${encodeURIComponent(chartId)}/calibrate`,
    {
      method: "POST",
      params: deviceId ? { device_id: deviceId } : undefined,
    }
  );
}

export function fetchLatestCalibration(
  chartId: string,
  deviceId?: string
): Promise<CalibrationResponse> {
  return fetchJson<CalibrationResponse>(
    `/charts/${encodeURIComponent(chartId)}/calibrate/latest`,
    { params: deviceId ? { device_id: deviceId } : undefined }
  );
}

export interface CompatibilityDimension {
  key: string;
  label: string;
  score: number;
  weight: number;
}

export interface CompatibilityReading {
  sections: Array<{ id: string; title: string; text: string }>;
  advice: string[];
  markdown?: string;
}

export interface JointAuspiciousDay {
  date: string;
  day_pillar: string;
  score: number;
  score_a: number;
  score_b: number;
  weather?: string;
  reasoning: string;
  recommended: boolean;
  best_hour?: {
    label?: string;
    clock?: string;
    score?: number;
  } | null;
}

export interface CompatibilityResponse {
  score: number;
  level: string;
  dimensions: CompatibilityDimension[];
  supports: string[];
  conflicts: string[];
  summary: string;
  reading?: CompatibilityReading;
  note?: string;
  profiles: {
    a: Record<string, unknown>;
    b: Record<string, unknown>;
  };
  joint_days?: JointAuspiciousDay[];
  joint_top?: JointAuspiciousDay[];
  ics?: string;
}

export function fetchCompatibility(
  baziA: string,
  genderA: string,
  baziB: string,
  genderB: string,
  options?: {
    includeJointDays?: boolean;
    includeIcs?: boolean;
    eventType?: string;
    dateFrom?: string;
    dateTo?: string;
    topN?: number;
  }
): Promise<CompatibilityResponse> {
  return fetchJson<CompatibilityResponse>("/bazi/compatibility", {
    method: "POST",
    body: JSON.stringify({
      bazi_a: baziA,
      gender_a: genderA,
      bazi_b: baziB,
      gender_b: genderB,
      include_joint_days: options?.includeJointDays ?? true,
      include_ics: options?.includeIcs ?? true,
      event_type: options?.eventType ?? "marriage",
      date_from: options?.dateFrom,
      date_to: options?.dateTo,
      top_n: options?.topN ?? 8,
    }),
  });
}
