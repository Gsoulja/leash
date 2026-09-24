// Open asks: loaded from the read model, then kept current from the event stream (LEASH-064).
// Stream events are journalled, and every /api/asks response is replayed with the events that arrived
// after that request started, so a slow response can't drop a new ask or revive a resolved one. The
// browser reconnects by itself with Last-Event-ID; after a reconnect the hook also reloads /api/asks.
// If the browser gives up (e.g. a 502 while the engine restarts), the hook reopens the stream with backoff.
// After every (re)open it reloads once more when the stream has settled (see SETTLE_MS).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { PATHS, api, type Ask, type AskCreatedData, type AskResolvedData } from "./client";

const KEY = ["asks"] as const;
const JOURNAL_LIMIT = 5000;
// The server sets its stream start point shortly after the connection opens; a change between our reload
// and that point would never be streamed. Reloading once more after this long closes that gap.
const SETTLE_MS = 2000;
const DETAILS_MS = 300;  // new asks arrive in bursts: one reload for the burst
const RETRY_FIRST_MS = 1000;
const RETRY_MAX_MS = 30000;

type Change = { kind: "created"; data: AskCreatedData } | { kind: "resolved"; data: AskResolvedData };

function fromCreated(data: AskCreatedData, known?: Ask): Ask {
  // An event carries only what the ask screen needs first; details come from /api/payments/{id}.
  const payment: Ask["payment"] = known?.payment ?? {
    authorization_id: data.authorization_id, run_id: "", merchant: { merchant_id: "", name: data.merchant_name, category: "", country: "" },
    sim_time: "", amount: data.billing_amount_chf, currency: "CHF", billing_amount_chf: data.billing_amount_chf, items: [],
    engine_verdict: "step_up", final_state: "waiting", resolved_by: null, customer_message: data.reasons.join(" "),
  };
  return {
    authorization_id: data.authorization_id, payment, reasons: data.reasons, passed: known?.passed ?? [],
    expires_at: data.expires_at, can_approve: data.can_approve,
    cannot_approve_reason: data.can_approve ? null : (known?.cannot_approve_reason ?? null),
  };
}

function apply(asks: Ask[], change: Change): Ask[] {
  if (change.kind === "resolved") return asks.filter((a) => a.authorization_id !== change.data.authorization_id);
  const known = asks.find((a) => a.authorization_id === change.data.authorization_id);
  const next = fromCreated(change.data, known);
  return known ? asks.map((a) => (a === known ? next : a)) : [...asks, next];
}

function read(event: Event): Record<string, unknown> | null {
  try {
    const data = (JSON.parse((event as MessageEvent).data) as { data?: unknown }).data;
    return data && typeof data === "object" ? (data as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

const isCreated = (d: Record<string, unknown>): d is AskCreatedData =>
  typeof d.authorization_id === "string" && typeof d.merchant_name === "string" &&
  typeof d.billing_amount_chf === "string" && Array.isArray(d.reasons) && typeof d.expires_at === "string" &&
  typeof d.can_approve === "boolean";
const isResolved = (d: Record<string, unknown>): d is AskResolvedData => typeof d.authorization_id === "string";

export function useAsks() {
  const client = useQueryClient();
  const journal = useRef<{ seq: number; change: Change }[]>([]);
  const seq = useRef(0);

  const query = useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const startedAt = seq.current;
      const { asks } = await api().asks();
      return journal.current.filter((j) => j.seq > startedAt).reduce((list, j) => apply(list, j.change), asks);
    },
  });
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;  // no stream (e.g. tests): /api/asks alone
    let source: EventSource | null = null;
    let retryMs = RETRY_FIRST_MS;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let settle: ReturnType<typeof setTimeout> | undefined;
    let details: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let opened = false;

    const record = (change: Change) => {
      journal.current.push({ seq: ++seq.current, change });
      if (journal.current.length > JOURNAL_LIMIT) journal.current.shift();
      client.setQueryData<Ask[]>(KEY, (asks) => (asks === undefined ? asks : apply(asks, change)));
    };

    const open = () => {
      source = new EventSource(PATHS.events);
      source.onopen = () => {
        setConnected(true);
        retryMs = RETRY_FIRST_MS;
        if (opened) void client.invalidateQueries({ queryKey: KEY });  // a reconnect: reload the current state
        opened = true;
        clearTimeout(settle);
        // Always a fresh request, even if a slow first load is still running (it may predate the stream).
        settle = setTimeout(() => {
          void client.cancelQueries({ queryKey: KEY }).then(() => client.refetchQueries({ queryKey: KEY }));
        }, SETTLE_MS);
      };
      source.onerror = () => {
        setConnected(false);
        if (source && source.readyState === EventSource.CLOSED && !stopped) {  // the browser gave up: reopen
          source.close();
          retry = setTimeout(open, retryMs);
          retryMs = Math.min(retryMs * 2, RETRY_MAX_MS);
        }
      };
      source.addEventListener("ask.created", (event) => {
        const data = read(event);
        if (data && isCreated(data)) {
          record({ kind: "created", data });
          // The event carries only what the prompt needs first; fetch the full ask (what passed, currency,
          // items) right after. The journal keeps a slow reply from dropping or reviving anything.
          clearTimeout(details);
          details = setTimeout(() => void client.invalidateQueries({ queryKey: KEY }), DETAILS_MS);
        }
      });
      source.addEventListener("ask.resolved", (event) => {
        const data = read(event);
        if (data && isResolved(data)) record({ kind: "resolved", data });
      });
    };

    open();
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearTimeout(settle);
      clearTimeout(details);
      source?.close();
    };
  }, [client]);

  return { asks: query.data ?? [], connected, isLoading: query.isLoading, error: query.error };
}
