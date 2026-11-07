import { useParams } from "react-router-dom";
import { ArtifactEditor } from "@/components/ArtifactEditor";
import { VoiceTrials } from "@/components/VoiceTrials";

export default function VoicePage() {
  const { id } = useParams() as { id: string };
  return (
    <div className="space-y-10">
      <VoiceTrials bookId={id} />
      <ArtifactEditor bookId={id} kind="voice" title="Voice"
        hint="Narrative register, exemplar paragraphs, anti-exemplars, rhythm rules." />
    </div>
  );
}
