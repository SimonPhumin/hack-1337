/** Run `fn` once calls have stopped for `ms` milliseconds. */
export function debounce<A extends unknown[]>(fn: (...args: A) => void, ms = 250) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return (...args: A): void => {
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, ms);
  };
}
