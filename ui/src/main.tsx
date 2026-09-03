import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import Home from "./routes/Home";
import SourceDetailPage from "./routes/SourceDetailPage";
import RawSourcePage from "./routes/RawSourcePage";
import EntryPage from "./routes/EntryPage";
import SectionPage from "./routes/SectionPage";
import ReviewPage from "./routes/ReviewPage";
import SuppliedContextPage from "./routes/SuppliedContextPage";
import "./index.css";
import "./prose.css";

const queryClient = new QueryClient();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("no #root element to mount into");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<Home />} />
            <Route path="sources/:id" element={<SourceDetailPage />} />
            <Route path="sources/:id/raw" element={<RawSourcePage />} />
            <Route
              path="subjects/:subjectId/entries/:entrySlug"
              element={<EntryPage />}
            />
            <Route path="sections/:sectionId" element={<SectionPage />} />
            <Route path="sections/:sectionId/review" element={<ReviewPage />} />
            <Route
              path="sections/:sectionId/supplied-context"
              element={<SuppliedContextPage />}
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
