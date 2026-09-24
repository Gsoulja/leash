// Client for the Leash policy API. Types are generated from solution/contracts/policy-api.yaml
// (`npm run gen:api`; src/api/schema.test.ts fails when they drift). Calls go to the relative /api base;
// in development Vite proxies them to the contract mock (LEASH-118), later to the real engine.
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Payment = Schemas["Payment"];
export type PaymentList = Schemas["PaymentList"];
export type PaymentDetail = Schemas["PaymentDetail"];
export type Ask = Schemas["Ask"];
export type AskList = Schemas["AskList"];
export type Spending = Schemas["Spending"];
export type MandateList = Schemas["MandateList"];
export type Mandate = Schemas["Mandate"];
export type Run = Schemas["Run"];
export type TightenRequest = Schemas["TightenRequest"];
export type HardRule = Schemas["HardRule"];
export type RunList = Schemas["RunList"];
export type MandateVersionList = Schemas["MandateVersionList"];
export type StreamEvent = Schemas["StreamEvent"];
export type AskCreatedData = Schemas["AskCreatedData"];
export type AskResolvedData = Schemas["AskResolvedData"];
export type PaymentDecidedData = Schemas["PaymentDecidedData"];
export type IntegrityAlertData = Schemas["IntegrityAlertData"];
export type Check = Schemas["Check"];
export type PolicyDraft = Schemas["PolicyDraft"];
export type PlatformDraft = Schemas["PlatformDraft"];
export type Question = Schemas["Question"];

export const PATHS = {
  drafts: "/api/policies/drafts",
  draft: "/api/policies/drafts/{draft_id}",
  draftAnswers: "/api/policies/drafts/{draft_id}/answers",
  draftSubmit: "/api/policies/drafts/{draft_id}/submit",
  draftConfirm: "/api/policies/drafts/{draft_id}/confirm",
  payments: "/api/payments",
  payment: "/api/payments/{authorization_id}",
  asks: "/api/asks",
  mandates: "/api/mandates",
  mandate: "/api/mandates/{mandate_id}",
  answer: "/api/asks/{authorization_id}/answer",
  runs: "/api/runs",
  run: "/api/runs/{run_id}",
  mandateVersions: "/api/mandates/{mandate_id}/versions",
  tighten: "/api/mandates/{mandate_id}/tighten",
  spending: "/api/spending",
  events: "/api/events",
} as const;

type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(`${code}: ${message}`);
  }
}

function withQuery(path: string, query: Record<string, string | undefined>): string {
  const params = Object.entries(query).filter(([, v]) => v !== undefined) as [string, string][];
  return params.length ? `${path}?${new URLSearchParams(params)}` : path;
}

export function api(fetcher: Fetcher = (url, init) => fetch(url, init)) {
  async function get<T>(path: string): Promise<T> {
    const response = await fetcher(path, { headers: { Accept: "application/json" } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = (body as { error?: { code?: string; message?: string } }).error ?? {};
      throw new ApiError(response.status, error.code ?? "http_error", error.message ?? response.statusText);
    }
    return body as T;
  }
  async function send<T>(path: string, payload: unknown, method: "POST" | "DELETE" = "POST"): Promise<T> {
    const response = await fetcher(path, method === "DELETE" ? { method, headers: { Accept: "application/json" } } : {
      method,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = (body as { error?: { code?: string; message?: string } }).error ?? {};
      throw new ApiError(response.status, error.code ?? "http_error", error.message ?? response.statusText);
    }
    return body as T;
  }
  const draftPath = (path: string, id: string) => path.replace("{draft_id}", encodeURIComponent(id));
  return {
    createDraft: (instruction: string) => send<PolicyDraft>(PATHS.drafts, { instruction }),
    draft: (id: string) => get<PolicyDraft>(draftPath(PATHS.draft, id)),
    answerDraft: (id: string, questionId: string, answer: string) =>
      send<PolicyDraft>(draftPath(PATHS.draftAnswers, id), { answers: [{ question_id: questionId, answer }] }),
    submitDraft: (id: string) => send<PlatformDraft>(draftPath(PATHS.draftSubmit, id), null),
    confirmDraft: (id: string) => send<Mandate>(draftPath(PATHS.draftConfirm, id), { confirmed: true }),
    payments: (runId?: string) => get<PaymentList>(withQuery(PATHS.payments, { run_id: runId })),
    payment: (id: string) => get<PaymentDetail>(PATHS.payment.replace("{authorization_id}", encodeURIComponent(id))),
    asks: () => get<AskList>(PATHS.asks),
    mandates: () => get<MandateList>(PATHS.mandates),
    mandate: (id: string) => get<Mandate>(PATHS.mandate.replace("{mandate_id}", encodeURIComponent(id))),
    tighten: (id: string, change: TightenRequest) =>
      send<Mandate>(PATHS.tighten.replace("{mandate_id}", encodeURIComponent(id)), change),
    revoke: (id: string) => send<Mandate>(PATHS.mandate.replace("{mandate_id}", encodeURIComponent(id)), null, "DELETE"),
    answerAsk: (id: string, decision: "approve" | "decline") =>
      send<Payment>(PATHS.answer.replace("{authorization_id}", encodeURIComponent(id)), { decision }),
    runs: () => get<RunList>(PATHS.runs),
    startRun: (scenarioId: string, mandateId: string) =>
      send<Run>(PATHS.runs, { scenario_id: scenarioId, mandate_id: mandateId }),
    run: (id: string) => get<Run>(PATHS.run.replace("{run_id}", encodeURIComponent(id))),
    mandateVersions: (id: string) =>
      get<MandateVersionList>(PATHS.mandateVersions.replace("{mandate_id}", encodeURIComponent(id))),
    spending: (runId?: string) => get<Spending>(withQuery(PATHS.spending, { run_id: runId })),
  };
}
