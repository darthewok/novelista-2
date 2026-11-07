"use client";
import { useParams, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PhaseStepper } from "@/components/PhaseStepper";

const PHASE_KEYS = ["seed", "world", "characters", "outline", "chapters", "export"] as const;

export default function BookLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname() ?? "";
  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => api.getBook(id) });

  const active = (PHASE_KEYS.find((k) => pathname.includes(`/${k}`)) ?? "seed") as string;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold truncate">{book?.title ?? "…"}</h1>
        <PhaseStepper bookId={id} active={active} />
      </div>
      <div>{children}</div>
    </div>
  );
}
