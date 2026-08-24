import { useEffect, useState } from "react";
import type { Distributor } from "../types";

interface Props {
  selectedId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
}

/**
 * Who the rep is about to meet. Chosen before recording starts — this id is
 * the tenant scope for every tool call, and it never comes from the model.
 */
export function DistributorPicker({ selectedId, disabled, onSelect }: Props) {
  const [options, setOptions] = useState<Distributor[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/distributors")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: Distributor[]) => {
        if (cancelled) return;
        setOptions(data);
        if (!selectedId && data.length > 0) onSelect(data[0].id);
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
    // Load once on mount; re-running on selection would fight the default.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="picker">
        <span className="picker-label">Meeting with</span>
        <span className="picker-error">
          could not load distributors ({error}) — is the database seeded?
        </span>
      </div>
    );
  }

  const selected = options.find((o) => o.id === selectedId);

  return (
    <div className="picker">
      <label className="picker-label" htmlFor="distributor">
        Meeting with
      </label>
      <select
        id="distributor"
        className="picker-select"
        value={selectedId ?? ""}
        disabled={disabled || options.length === 0}
        onChange={(e) => onSelect(e.target.value)}
      >
        {options.length === 0 && <option value="">loading…</option>}
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      {selected && (
        <span className="picker-meta">
          {selected.region} · {selected.aum_tier} · {selected.risk_appetite} risk
        </span>
      )}
    </div>
  );
}
