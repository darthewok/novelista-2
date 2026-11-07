import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Providers } from "./providers";
import App from "./App";
import "./index.css";

// Data router (needed for useBlocker); App keeps its own <Routes>.
const router = createBrowserRouter([{ path: "*", element: <Providers><App /></Providers> }]);

createRoot(document.getElementById("root")!).render(<RouterProvider router={router} />);
