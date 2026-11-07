import { useParams } from "react-router-dom";
import { ArtifactEditor } from "@/components/ArtifactEditor";

export default function CharactersPage() {
  const { id } = useParams() as { id: string };
  return <ArtifactEditor bookId={id} kind="characters" title="Characters"
    hint="Wound / Want / Need / Lie. Speech signatures. Relationships." />;
}
