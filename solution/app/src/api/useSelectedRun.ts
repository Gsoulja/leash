// Which run the app is describing (LEASH-133). Lifted out of Cockpit.tsx by LEASH-097 so that the phone
// and the engine inspector beside it always talk about the same run: one selection, shared by both.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Run } from "./client";

export type RunSelection = {
  runs: Run[];
  run?: Run;
  runId: string | null;
  select: (id: string) => void;
  loading: boolean;
  error: boolean;
};

export function useSelectedRun(): RunSelection {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api().runs() });
  const [chosen, setChosen] = useState<string | null>(null);
  const list = runs.data?.runs ?? [];
  const first = runs.data?.current_run_id ?? list[0]?.run_id ?? null;
  useEffect(() => {  // pin the run shown first, so a newer run starting later doesn't take over the screen
    if (chosen === null && first !== null) setChosen(first);
  }, [chosen, first]);
  const runId = chosen ?? first;
  return { runs: list, run: list.find((r) => r.run_id === runId), runId, select: setChosen,
           loading: runs.isLoading, error: runs.isError };
}
