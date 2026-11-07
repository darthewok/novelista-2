import { useParams } from "react-router-dom";
import { ArtifactEditor } from "@/components/ArtifactEditor";

export default function WorldPage() {
  const { id } = useParams() as { id: string };
  return <ArtifactEditor bookId={id} kind="world" title="World"
    hint="Cosmology, geography, peoples, history, open story hooks." />;
}
