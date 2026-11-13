import { useEffect, useState } from "react";
import { Sun, Moon, Eye, SunMoon, Check } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { THEMES, storedTheme, setTheme, onThemeChange } from "@/lib/theme";

const ICONS = { dark: Moon, sun: Sun, night: Eye, auto: SunMoon };

// Header button: one tap opens the four themes, one tap picks.
export default function ThemePicker({ className = "" }) {
  const [choice, setChoice] = useState(storedTheme());
  const [open, setOpen] = useState(false);
  useEffect(() => onThemeChange(setChoice), []);
  const Icon = ICONS[choice] || Moon;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center justify-center rounded-md text-slate-400 hover:text-cyan-300 hover:bg-cyan-500/10 w-8 h-8 sm:w-9 sm:h-9 ${className}`}
          title="Colour theme"
          aria-label="Colour theme"
          data-testid="theme-picker"
        >
          <Icon className="w-4 h-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-1 bg-slate-900 border-slate-700 text-slate-200">
        {THEMES.map((t) => {
          const I = ICONS[t.id];
          const on = t.id === choice;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => { setTheme(t.id); setOpen(false); }}
              className={`w-full flex items-start gap-3 rounded px-3 py-2.5 text-left hover:bg-slate-800 ${on ? "bg-slate-800" : ""}`}
              data-testid={`theme-${t.id}`}
            >
              <I className="w-4 h-4 mt-0.5 text-cyan-400" />
              <span className="flex-1">
                <span className="block text-sm font-semibold text-white">{t.label}</span>
                <span className="block text-xs text-slate-400">{t.hint}</span>
              </span>
              {on && <Check className="w-4 h-4 mt-0.5 text-cyan-400" />}
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}
