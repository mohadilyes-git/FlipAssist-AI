// The app: three screens, each with its own address (#message, #listing, #home),
// and AlertFlip's floating dock to move between them.
import { type ComponentType, useEffect, useState } from "react";
import { HomeScreen } from "./screens/HomeScreen";
import { ListingScreen } from "./screens/ListingScreen";
import { MessageScreen } from "./screens/MessageScreen";
import { MeterIcon, SparkleIcon, TagIcon } from "./ui";

type Tab = "message" | "listing" | "home";
const TABS: { tab: Tab; label: string; icon: ComponentType }[] = [
  { tab: "message", label: "Message", icon: SparkleIcon },
  { tab: "listing", label: "List on eBay", icon: TagIcon },
  { tab: "home", label: "Home", icon: MeterIcon },
];

const fromHash = (): Tab => {
  const found = window.location.hash.slice(1);
  return TABS.some((t) => t.tab === found) ? (found as Tab) : "message";
};

export function App() {
  const [tab, setTab] = useState<Tab>(fromHash);
  useEffect(() => {
    const follow = () => setTab(fromHash());
    window.addEventListener("hashchange", follow);
    return () => window.removeEventListener("hashchange", follow);
  }, []);
  const go = (next: Tab) => {
    window.location.hash = next;
    setTab(next);
  };
  return (
    <>
      <main>
        {tab === "message" && <MessageScreen />}
        {tab === "listing" && <ListingScreen />}
        {tab === "home" && <HomeScreen go={go} />}
      </main>
      <nav className="dock" aria-label="Screens">
        {TABS.map(({ tab: t, label, icon: Icon }) => (
          <a key={t} href={`#${t}`} aria-current={tab === t ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              go(t);
            }}>
            <Icon />
            <span>{label}</span>
          </a>
        ))}
      </nav>
    </>
  );
}
