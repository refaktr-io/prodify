import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";

function Home() {
  return (
    <main>
      <h1>Prodify fixture</h1>
      <p data-testid="home">Built by the content deployer.</p>
      <Link to="/about">About</Link>
    </main>
  );
}

function About() {
  return <p data-testid="about">Client-side route served via the SPA fallback.</p>;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/about" element={<About />} />
    </Routes>
  </BrowserRouter>
);
