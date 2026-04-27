import { useState } from "react";
import { Panel } from "./Panel";
import { Watchlist } from "./Watchlist";
import "./cockpit.css";

export function CockpitPage() {
  const [selectedSlot, setSelectedSlot] = useState(2);

  return (
    <main className="main">
      <Watchlist selectedId={selectedSlot} onSelect={setSelectedSlot} />
      <Panel />
    </main>
  );
}
