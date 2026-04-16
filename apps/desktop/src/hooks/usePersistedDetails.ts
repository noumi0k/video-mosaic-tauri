import { useCallback, useEffect, useState, type SyntheticEvent } from "react";

const STORAGE_PREFIX = "auto-mosaic:inspector-open:";

function readStored(sectionId: string, fallback: boolean): boolean {
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${sectionId}`);
    if (raw === null) return fallback;
    return raw === "1";
  } catch {
    return fallback;
  }
}

export function usePersistedDetails(
  sectionId: string,
  defaultOpen = true,
): { open: boolean; onToggle: (event: SyntheticEvent<HTMLDetailsElement>) => void } {
  const [open, setOpen] = useState<boolean>(() => readStored(sectionId, defaultOpen));

  useEffect(() => {
    try {
      window.localStorage.setItem(`${STORAGE_PREFIX}${sectionId}`, open ? "1" : "0");
    } catch {
      // ignore quota / security errors — UI keeps working, just not persisted.
    }
  }, [sectionId, open]);

  const onToggle = useCallback((event: SyntheticEvent<HTMLDetailsElement>) => {
    setOpen((event.currentTarget as HTMLDetailsElement).open);
  }, []);

  return { open, onToggle };
}
