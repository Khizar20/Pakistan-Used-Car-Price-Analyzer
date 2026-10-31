import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { clearCache, loadBundle } from "./lib/data";
import type { Bundle } from "./lib/data";
import { date } from "./lib/format";
import tokens from "../design/tokens.json";
import { About, Drivers, Drops, Fair, Market, Seasons } from "./pages";

const routes = {
  market: ["Market", Market],
  drops: ["Price drops", Drops],
  seasons: ["Seasons", Seasons],
  drivers: ["Drivers", Drivers],
  fair: ["Fair price", Fair],
  about: ["About the data", About],
} as const;
type Route = keyof typeof routes;
function route(): Route {
  const hash = location.hash.slice(1);
  return Object.hasOwn(routes, hash) ? (hash as Route) : "market";
}
function initialTheme(): "light" | "dark" {
  try {
    const saved = localStorage.getItem("tracker-theme");
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    /* Browser storage is optional. */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}
export default function App() {
  const [page, setPage] = useState<Route>(route);
  const [theme, setTheme] = useState(initialTheme);
  const [full, setFull] = useState(false);
  const [bundle, setBundle] = useState<Bundle>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const main = useRef<HTMLElement>(null);
  const manuallyChosen = useRef(false);
  useEffect(() => {
    const change = () => {
      setPage(route());
      main.current?.focus();
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    document.title = `${routes[page][0]} · Pakistan used-car price tracker`;
  }, [page]);
  useEffect(() => {
    document.documentElement.style.colorScheme = theme;
  }, [theme]);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const change = () => {
      let saved: string | null = null;
      try {
        saved = localStorage.getItem("tracker-theme");
      } catch {
        /* Storage is optional. */
      }
      if (!manuallyChosen.current && saved !== "light" && saved !== "dark")
        setTheme(media.matches ? "dark" : "light");
    };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    manuallyChosen.current = true;
    setTheme(next);
    try {
      localStorage.setItem("tracker-theme", next);
    } catch {
      /* The current selection still works. */
    }
  }
  useEffect(() => {
    let active = true;
    loadBundle()
      .then((value) => {
        if (active) {
          setBundle(value);
          setError("");
        }
      })
      .catch((caught: unknown) => {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : "The data could not be loaded. Please retry.",
          );
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  const Page = routes[page][1];
  const palette = Object.fromEntries(
    Object.entries(tokens[theme]).map(([key, value]) => [`--${key}`, value]),
  ) as CSSProperties;
  return (
    <div className="app" style={palette} data-theme={theme}>
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          main.current?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className="rail">
        <a
          href="#market"
          className="brand"
          aria-label="Pakistan Car prices home"
        >
          <svg aria-hidden="true" width="32" height="38" viewBox="0 0 32 38">
            <rect width="32" height="38" rx="4" fill="var(--motorway)" />
            <path
              d="M10 29 13 9M22 29 19 9M16 10v4m0 4v4m0 4v3"
              stroke="var(--paper)"
              strokeWidth="2"
            />
          </svg>
          <span>
            Pakistan
            <br />
            <strong>Car prices</strong>
          </span>
        </a>
        <nav aria-label="Main navigation">
          {Object.entries(routes).map(([key, [label]]) => (
            <a
              key={key}
              href={`#${key}`}
              aria-current={page === key ? "page" : undefined}
            >
              <span className="nav-mark" aria-hidden="true" />
              {label}
            </a>
          ))}
        </nav>
        <div className="rail-note">
          <span className="status-dot" />
          Independent observations
          <p>
            A view of asking prices.
            <br />A clearer place to start.
          </p>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <span>
            PakWheels observations{" "}
            <span className="header-date">
              / {bundle ? date(bundle.meta.data.date_end) : "Loading data"}
            </span>
          </span>
          <div className="preferences">
            <button
              onClick={() => {
                clearCache();
                setBundle(undefined);
                setError("");
                setAttempt((value) => value + 1);
              }}
            >
              Refresh data
            </button>
            <label>
              <input
                type="checkbox"
                checked={full}
                onChange={(event) => setFull(event.target.checked)}
              />
              Full prices
            </label>
            <button
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
              onClick={toggleTheme}
            >
              {theme === "light" ? "Dark theme" : "Light theme"}
            </button>
          </div>
        </header>
        <main id="main" ref={main} tabIndex={-1}>
          {error ? (
            <section className="load-state" role="alert">
              <h1>We couldn’t load a complete update</h1>
              <p>{error}</p>
              <button
                className="primary"
                onClick={() => {
                  clearCache();
                  setError("");
                  setBundle(undefined);
                  setAttempt((value) => value + 1);
                }}
              >
                Retry
              </button>
            </section>
          ) : bundle ? (
            <Page key={page} bundle={bundle} full={full} />
          ) : (
            <section className="load-state" role="status">
              <h1>Loading the market observations</h1>
              <p>Preparing one verified update.</p>
              <div className="loading-rule" />
            </section>
          )}
        </main>
        <footer>
          <span>Asking prices, not sale prices.</span>
          <a href="#about">Understand the data</a>
          <span>Pakistan used-car price tracker</span>
        </footer>
      </div>
    </div>
  );
}
