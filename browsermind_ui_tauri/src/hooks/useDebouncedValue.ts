import { useEffect, useState } from "react";

/**
 * Returns `value` after it has been stable for `delayMs` milliseconds.
 * Useful for debouncing search inputs before firing queries.
 */
export function useDebouncedValue<T>(value: T, delayMs = 200): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}
