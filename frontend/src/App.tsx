// The app: a Mac-style window with five screens in a sidebar, each at its own
// address (#home, #message, #style, #price, #listing) so a refresh keeps your place,
// light or dark as your device is (or as you switch it), and on first launch
// "Set up your style" before any of them.
import { type ComponentType, useCallback, useEffect, useMemo, useState } from "react";
import { api, type Health, type Style } from "./api";
import { HomeScreen } from "./screens/HomeScreen";
import { ListingScreen } from "./screens/ListingScreen";
import { MessageScreen } from "./screens/MessageScreen";
import { PriceScreen, type SentListing } from "./screens/PriceScreen";
import { Setup, type SetupStep } from "./screens/Setup";
import { StyleScreen } from "./screens/StyleScreen";
import { GaugeIcon, Logo, MoonIcon, PenIcon, PoundIcon, SparkleIcon, SunIcon, TagIcon } from "./ui";

export type Tab = "message" | "price" | "listing" | "home" | "style";
// in this order (4 Oct): where you start, what you do most, what it learned from you, what the item is
// worth (its own tab), then listing on eBay
const TABS: { tab: Tab; label: string; icon: ComponentType<{ size?: number; stroke?: number }> }[] = [
  { tab: "home", label: "Home", icon: GaugeIcon },
  { tab: "message", label: "AI message", icon: SparkleIcon },
  { tab: "style", label: "My style", icon: PenIcon },  // "My style", not "Your style" (14 Oct, the owner)
  { tab: "price", label: "AI UK price estimate", icon: PoundIcon },
  { tab: "listing", label: "List on eBay", icon: TagIcon },
];
export const SETUP_DONE = "flipassist.setupDone";
export const THEME = "flipassist.theme";
type Theme = "light" | "dark";
/** /health's answer, or "down" when the API didn't answer at all */
export type Running = Health | "down" | null;

// what's remembered in this browser; a private window may refuse, and then it's just not remembered
const stored = (key: string) => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};
const store = (key: string, value: string) => {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // nothing to do: it's forgotten when the window closes
  }
};

/** In FlipAssist's own Mac window (launcher/), the window is the app: no desk around
 * it, the Mac's traffic lights in place of drawn ones, and its top bar to drag it by. */
export function markShell(page: Window = window) {
  if ("flipassistShell" in page) document.documentElement.dataset.shell = "window";
}

const fromHash = (): Tab => {
  const found = window.location.hash.slice(1);
  return TABS.some((t) => t.tab === found) ? (found as Tab) : "home";  // it opens on Home
};

/** Light or dark: your device's choice, until you switch it here. */
function useTheme(): [Theme, () => void] {
  const darkMac = useMemo(() => window.matchMedia?.("(prefers-color-scheme: dark)"), []);
  const [mac, setMac] = useState<Theme>(darkMac?.matches ? "dark" : "light");
  const [picked, setPicked] = useState<Theme | null>(() => {
    const found = stored(THEME);
    return found === "light" || found === "dark" ? found : null;
  });
  useEffect(() => {
    if (!darkMac) return;
    const follow = () => setMac(darkMac.matches ? "dark" : "light");
    darkMac.addEventListener("change", follow);
    return () => darkMac.removeEventListener("change", follow);
  }, [darkMac]);
  const theme = picked ?? mac;
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setPicked(next);
    store(THEME, next);
  };
  return [theme, toggle];
}

export function App() {
  const [tab, setTab] = useState<Tab>(fromHash);
  const [setup, setSetup] = useState<SetupStep | null>(() => (stored(SETUP_DONE) ? null : "welcome"));
  // the setup was opened from Your style (Do setup, Redo setup): leaving it goes back there, not to Home
  const [again, setAgain] = useState(false);
  const [theme, toggleTheme] = useTheme();
  const [style, setStyle] = useState<Style | null>(null);
  const [running, setRunning] = useState<Running>(null);
  // a listing AI message sent to the price tab (4 Nov): a new object each time, so the tab checks it again
  const [sentToPrice, setSentToPrice] = useState<SentListing | null>(null);

  const loadStyle = useCallback(async () => {
    try {
      setStyle(await api.style());
    } catch {
      // each screen says what's wrong when it can't reach the API
    }
  }, []);
  const loadRunning = useCallback(async () => {
    try {
      setRunning(await api.health());
    } catch {
      setRunning("down");
    }
  }, []);

  useEffect(() => {
    void loadRunning();
    const every = window.setInterval(() => void loadRunning(), 30_000);
    api.style().then((found) => {
      setStyle(found);
      // the API already knows your style (set up in another browser, or learned from a CSV): no need to ask again
      if (found.count && !stored(SETUP_DONE)) {
        store(SETUP_DONE, "1");
        setSetup((now) => (now === "welcome" ? null : now));
      }
    }, () => undefined);
    const follow = () => setTab(fromHash());
    window.addEventListener("hashchange", follow);
    return () => {
      window.clearInterval(every);
      window.removeEventListener("hashchange", follow);
    };
  }, [loadRunning]);

  const go = useCallback((next: Tab) => {
    window.location.hash = next;
    setTab(next);
  }, []);
  // leaving the setup, done or not: back to Your style when it was opened from there, else on to Home (first launch,
  // skipped or done: Your style's Do setup is there for later)
  const leave = () => {
    store(SETUP_DONE, "1");
    setSetup(null);
    setAgain(false);
    go(again ? "style" : "home");
  };

  const name = setup ? "Set up my style" : TABS.find((t) => t.tab === tab)!.label;
  useEffect(() => {
    document.title = `FlipAssist · ${name}`;
  }, [name]);
  const count = style?.count ?? 0;

  return (
    <div className="desk">
      <div className="window">
        <header className="titlebar">
          <span className="lights" aria-hidden="true"><span /><span /><span /></span>
          <span className="window-title">FlipAssist · {name}</span>
          <StatusPill running={running} />
        </header>
        <div className="window-body">
          {!setup && (
            <aside className="sidebar">
              <a className="logo" href="#home" onClick={(e) => {
                e.preventDefault();
                go("home");
              }}>
                <Logo />
                <span className="wordmark">
                  <strong>Flip<span>Assist</span></strong>
                  <small>by AlertFlip</small>
                </span>
              </a>
              <nav className="nav" aria-label="Screens">
                {TABS.map(({ tab: t, label, icon: Icon }) => (
                  <a key={t} href={`#${t}`} aria-current={tab === t ? "page" : undefined} onClick={(e) => {
                    e.preventDefault();
                    go(t);
                  }}>
                    <Icon size={17} stroke={2.1} />
                    <span>{label}</span>
                  </a>
                ))}
              </nav>
              <div className="spacer" />
              <a className="style-link" href="#style" onClick={(e) => {
                e.preventDefault();
                go("style");
              }}>
                <span className="caps">My style</span>
                <strong>Learning from {count} of your messages</strong>
                <span>See what it learned</span>
              </a>
              <button type="button" className="theme-button" onClick={toggleTheme}>
                {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
                {theme === "dark" ? "Light mode" : "Dark mode"}
              </button>
            </aside>
          )}
          <main className="content">
            <div className="column">
              {setup ? (
                <Setup step={setup} go={setSetup} style={style} onLearned={loadStyle} onLeave={leave} again={again} />
              ) : (
                <>
                  {/* the screens you type into stay put while you look elsewhere; the others load fresh */}
                  <div className="screen" hidden={tab !== "message"}>
                    <MessageScreen onApproved={loadStyle} onCheckPrice={(title, description) => {
                      setSentToPrice({ title, description });
                      go("price");
                    }} />
                  </div>
                  <div className="screen" hidden={tab !== "price"}><PriceScreen sent={sentToPrice} /></div>
                  <div className="screen" hidden={tab !== "listing"}>
                    <ListingScreen writer={running && running !== "down" ? running.listing_model : undefined}
                      reader={running && running !== "down" ? running.listing_reader : undefined} />
                  </div>
                  {tab === "home" && <HomeScreen go={go} count={count} running={running} reload={loadRunning} />}
                  {tab === "style" && (
                    <StyleScreen style={style} reload={loadStyle} setUp={() => {
                      setAgain(true);
                      setSetup("welcome");
                    }} />
                  )}
                </>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

/** Top right of the window: whether Ollama, which runs FlipAssist's models and Gemma 3 4B on this Mac, is
 * there to read and write. */
function StatusPill({ running }: { running: Running }) {
  if (running === null) return <span />;
  if (running === "down") return <span className="status-pill down">API not running</span>;
  return running.local_running
    ? <span className="status-pill">Ollama running</span>
    : <span className="status-pill off">Ollama not running</span>;
}
