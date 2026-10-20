// matchMedia stub so tests can switch prefers-reduced-motion on and off.
let reduced = false;

export function setReducedMotion(value: boolean): void {
  reduced = value;
}

export function resetMotion(): void {
  reduced = false;
}

export function installMatchMedia(): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes('prefers-reduced-motion') ? reduced : false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}
