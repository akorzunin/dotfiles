#!/usr/bin/env python3
from pathlib import Path

pkg = Path.home() / ".pi/agent/npm/node_modules/@pi-unipi/notify"
if not pkg.exists():
    raise SystemExit("@pi-unipi/notify is not installed")


def patch(rel, edits):
    path = pkg / rel
    text = path.read_text()
    original = text
    for marker, old, new in edits:
        if marker in text:
            continue
        if old not in text:
            raise SystemExit(f"patch failed: {rel}: missing block for {marker}")
        text = text.replace(old, new, 1)
    if text != original:
        path.write_text(text)
        print(f"patched {rel}")


patch("types.ts", [
    ("soundPath?: string;", '''export interface NativeConfig {
  /** Whether native notifications are enabled */
  enabled: boolean;
  /** Windows appID to show instead of "SnoreToast" */''', '''export interface NativeConfig {
  /** Whether native notifications are enabled */
  enabled: boolean;
  /** Optional sound file to play with native notifications */
  soundPath?: string;
  /** Windows appID to show instead of "SnoreToast" */'''),
])

patch("settings.ts", [
    ('soundPath: "~/.unipi/config/notify/complete.wav"', '''  native: {
    enabled: true,
    suppressWhenFocused: false,
  },''', '''  native: {
    enabled: true,
    soundPath: "~/.unipi/config/notify/complete.wav",
    suppressWhenFocused: false,
  },'''),
])

patch("platforms/native.ts", [
    ('import { execFile } from "child_process";', '''import notifier from "node-notifier";
import { isWindowFocused } from "./focus.js";''', '''import notifier from "node-notifier";
import { execFile } from "child_process";
import { existsSync } from "fs";
import { homedir, platform } from "os";
import { isWindowFocused } from "./focus.js";'''),
    ("soundPath?: string;", '''export interface NativeNotificationOptions {
  /** Windows appID to show instead of "SnoreToast" */
  windowsAppId?: string;''', '''export interface NativeNotificationOptions {
  /** Optional sound file to play with native notifications */
  soundPath?: string;
  /** Windows appID to show instead of "SnoreToast" */
  windowsAppId?: string;'''),
    ("function playSound", '''        } else {
          resolve();
        }
      }
    );
  });
}''', '''        } else {
          playSound(options?.soundPath);
          resolve();
        }
      }
    );
  });
}

function playSound(soundPath?: string): void {
  if (!soundPath) return;
  const file = soundPath.replace(/^~(?=$|\\/)/, homedir());
  if (!existsSync(file)) return;

  const command = platform() === "darwin" ? "afplay" : "paplay";
  execFile(command, [file], (err) => {
    if (!err || platform() === "darwin") return;
    execFile("aplay", [file], () => {});
  });
}'''),
])

patch("events.ts", [
    ("soundPath: config.native.soundPath", '''      await sendNativeNotification(title, message, {
        windowsAppId: config.native.windowsAppId,
        suppressWhenFocused: config.native.suppressWhenFocused,
      });''', '''      await sendNativeNotification(title, message, {
        soundPath: config.native.soundPath,
        windowsAppId: config.native.windowsAppId,
        suppressWhenFocused: config.native.suppressWhenFocused,
      });'''),
])

patch("tui/settings-overlay.ts", [
    ("native, gotify, telegram, ntfy + sound + suppress", '''    if (this.section === "platforms") return 5; // native, gotify, telegram, ntfy + suppress option''', '''    if (this.section === "platforms") return 6; // native, gotify, telegram, ntfy + sound + suppress option'''),
    ("// sound toggle", '''      } else {
        // suppressWhenFocused toggle (index 4)
        this.config.native.suppressWhenFocused = !this.config.native.suppressWhenFocused;
      }''', '''      } else if (this.selectedIndex === 4) {
        // sound toggle
        this.config.native.soundPath = this.config.native.soundPath
          ? undefined
          : "~/.unipi/config/notify/complete.wav";
      } else {
        // suppressWhenFocused toggle (index 5)
        this.config.native.suppressWhenFocused = !this.config.native.suppressWhenFocused;
      }'''),
    ("// suppressWhenFocused toggle (index 5)", '''    // suppressWhenFocused toggle (index 4)
    {
      const i = platforms.length;
      const isSelected = i === this.selectedIndex;
      const isEnabled = this.config.native.suppressWhenFocused === true;
      const toggleOn = this.fg("success", "●");
      const toggleOff = this.fg("dim", "○");
      const toggle = isEnabled ? toggleOn : toggleOff;
      const label = isSelected
        ? this.bold("Suppress when focused")
        : this.fg("dim", "Suppress when focused");
      const detail = this.fg("dim", isEnabled ? "Windows only — terminal in foreground → skip" : "Windows only");

      lines.push(
        this.frameLine(
          `${isSelected ? this.fg("accent", "▸") : " "} ${toggle} ${label}  ${detail}`,
          innerWidth
        )
      );
    }''', '''    // sound toggle (index 4)
    {
      const i = platforms.length;
      const isSelected = i === this.selectedIndex;
      const isEnabled = Boolean(this.config.native.soundPath);
      const toggleOn = this.fg("success", "●");
      const toggleOff = this.fg("dim", "○");
      const toggle = isEnabled ? toggleOn : toggleOff;
      const label = isSelected ? this.bold("Sound") : this.fg("dim", "Sound");
      const detail = this.fg("dim", this.config.native.soundPath ?? "Off");

      lines.push(
        this.frameLine(
          `${isSelected ? this.fg("accent", "▸") : " "} ${toggle} ${label}  ${detail}`,
          innerWidth
        )
      );
    }

    // suppressWhenFocused toggle (index 5)
    {
      const i = platforms.length + 1;
      const isSelected = i === this.selectedIndex;
      const isEnabled = this.config.native.suppressWhenFocused === true;
      const toggleOn = this.fg("success", "●");
      const toggleOff = this.fg("dim", "○");
      const toggle = isEnabled ? toggleOn : toggleOff;
      const label = isSelected
        ? this.bold("Suppress when focused")
        : this.fg("dim", "Suppress when focused");
      const detail = this.fg("dim", isEnabled ? "Windows only — terminal in foreground → skip" : "Windows only");

      lines.push(
        this.frameLine(
          `${isSelected ? this.fg("accent", "▸") : " "} ${toggle} ${label}  ${detail}`,
          innerWidth
        )
      );
    }'''),
])

print("notify sound patch ok")
