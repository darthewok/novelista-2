"use client";
import { useParams } from "next/navigation";
import { ArtifactEditor } from "@/components/ArtifactEditor";

export default function WorldPage() {
  const { id } = useParams<{ id: string }>();
  return <ArtifactEditor bookId={id} kind="world" title="World"
    hint="Cosmology, geography, peoples, history, open story hooks." />;
}
