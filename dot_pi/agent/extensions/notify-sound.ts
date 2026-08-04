import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const soundPath = process.env.PI_NOTIFY_SOUND ?? join(
  homedir(),
  ".unipi/config/notify/complete.wav",
);
const players = process.platform === "darwin"
  ? ["afplay"]
  : ["pw-play", "paplay", "aplay"];

function playSound(index = 0): void {
  const player = players[index];
  if (!player || !existsSync(soundPath)) return;

  execFile(player, [soundPath], (error) => {
    if (error) playSound(index + 1);
  });
}

export default function (pi: {
  events: { on(name: string, handler: (payload: unknown) => void): unknown };
}) {
  pi.events.on("unipi:notify:sent", (payload) => {
    const event = payload as { success?: boolean; platforms?: string[] };
    if (
      event.success &&
      event.platforms?.includes("native") &&
      !event.suppressedPlatforms?.includes("native")
    ) playSound();
  });
}
