"use client";
import { useParams } from "next/navigation";
import { ArtifactEditor } from "@/components/ArtifactEditor";

export default function CharactersPage() {
  const { id } = useParams<{ id: string }>();
  return <ArtifactEditor bookId={id} kind="characters" title="Characters"
    hint="Wound / Want / Need / Lie. Speech signatures. Relationships." />;
}
