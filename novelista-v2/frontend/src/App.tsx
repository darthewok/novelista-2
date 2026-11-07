import { Route, Routes } from "react-router-dom";
import Layout from "./Layout";
import Dashboard from "./pages/dashboard";
import NewBookPage from "./pages/books/new";
import SettingsPage from "./pages/settings";
import BookLayout from "./pages/books/book/layout";
import SeedPage from "./pages/books/book/seed";
import WorldPage from "./pages/books/book/world";
import CharactersPage from "./pages/books/book/characters";
import VoicePage from "./pages/books/book/voice";
import CanonPage from "./pages/books/book/canon";
import OutlinePage from "./pages/books/book/outline";
import ChaptersIndex from "./pages/books/book/chapters";
import ChapterPage from "./pages/books/book/chapter";
import ExportPage from "./pages/books/book/export";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/books/new" element={<NewBookPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/books/:id" element={<BookLayout />}>
          <Route path="seed" element={<SeedPage />} />
          <Route path="voice" element={<VoicePage />} />
          <Route path="world" element={<WorldPage />} />
          <Route path="characters" element={<CharactersPage />} />
          <Route path="canon" element={<CanonPage />} />
          <Route path="outline" element={<OutlinePage />} />
          <Route path="chapters" element={<ChaptersIndex />} />
          <Route path="chapters/:n" element={<ChapterPage />} />
          <Route path="export" element={<ExportPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
