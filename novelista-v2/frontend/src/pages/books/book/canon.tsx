import { useParams } from "react-router-dom";
import { ArtifactEditor } from "@/components/ArtifactEditor";

export default function CanonPage() {
  const { id } = useParams() as { id: string };
  return <ArtifactEditor bookId={id} kind="canon" title="Canon"
    hint="Facts that must stay true: names, dates, rules, relationships." />;
}
