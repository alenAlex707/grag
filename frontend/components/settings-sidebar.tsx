import { Network, PanelLeft, Search, Sparkles } from "lucide-react";

import type { RetrievalSettings } from "@/types";

interface SettingsSidebarProps {
  settings: RetrievalSettings;
  onChange: (settings: RetrievalSettings) => void;
}

export function SettingsSidebar({
  settings,
  onChange,
}: SettingsSidebarProps) {
  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-white/8 bg-[#0b0d0f]/90 px-5 py-5 md:h-screen md:w-72 md:border-r md:border-b-0 md:px-6 md:py-7">
      <div className="flex items-center gap-3">
        <div className="grid size-10 place-items-center rounded-xl bg-lime-300 text-[#10120f] shadow-[0_0_28px_rgba(190,242,100,0.18)]">
          <Network className="size-5" strokeWidth={2.25} />
        </div>
        <div>
          <p className="text-[10px] font-semibold tracking-[0.24em] text-lime-300 uppercase">
            Knowledge studio
          </p>
          <h1 className="text-xl font-semibold tracking-tight text-white">Grag</h1>
        </div>
      </div>

      <div className="mt-6 hidden md:block">
        <p className="max-w-48 text-sm leading-6 text-zinc-500">
          Answers grounded in your graph and source documents.
        </p>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 md:mt-12 md:grid-cols-1">
        <SettingCard
          icon={<Search className="size-4" />}
          label="Semantic depth"
          value={`${settings.topK} chunks`}
        >
          <input
            aria-label="Semantic search result count"
            className="range-control"
            max={20}
            min={1}
            onChange={(event) =>
              onChange({ ...settings, topK: Number(event.target.value) })
            }
            type="range"
            value={settings.topK}
          />
          <div className="mt-2 flex justify-between font-mono text-[10px] text-zinc-600">
            <span>01</span>
            <span>20</span>
          </div>
        </SettingCard>

        <SettingCard
          icon={<PanelLeft className="size-4" />}
          label="Graph reach"
          value={`${settings.graphHops} hop${settings.graphHops === 1 ? "" : "s"}`}
        >
          <div className="mt-3 grid grid-cols-2 gap-2">
            {[1, 2].map((hop) => (
              <button
                className={`rounded-lg border px-3 py-2 text-xs font-semibold transition ${
                  settings.graphHops === hop
                    ? "border-lime-300/50 bg-lime-300/10 text-lime-200"
                    : "border-white/8 bg-white/[0.025] text-zinc-500 hover:text-zinc-300"
                }`}
                key={hop}
                onClick={() => onChange({ ...settings, graphHops: hop })}
                type="button"
              >
                {hop} hop{hop === 1 ? "" : "s"}
              </button>
            ))}
          </div>
        </SettingCard>
      </div>

      <div className="mt-auto hidden rounded-xl border border-white/8 bg-white/[0.025] p-4 md:block">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-300">
          <Sparkles className="size-3.5 text-lime-300" />
          Hybrid retrieval
        </div>
        <p className="mt-2 text-xs leading-5 text-zinc-600">
          ChromaDB semantic search fused with NetworkX relationships.
        </p>
      </div>
    </aside>
  );
}

function SettingCard({
  children,
  icon,
  label,
  value,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <section className="rounded-xl border border-white/8 bg-white/[0.018] p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-zinc-500">
          {icon}
          <span className="text-[11px] font-medium tracking-wide uppercase">
            {label}
          </span>
        </div>
        <span className="font-mono text-[11px] text-zinc-300">{value}</span>
      </div>
      {children}
    </section>
  );
}
