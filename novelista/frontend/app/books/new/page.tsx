import { SeedForm } from "@/components/SeedForm";

export default function NewBookPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">New book</h1>
        <p className="text-slate-400 mt-1">
          All fields are optional. Leave the idea blank and we'll brainstorm 10 candidates with you.
        </p>
      </div>
      <SeedForm />
    </div>
  );
}
