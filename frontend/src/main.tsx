import '@fontsource/plus-jakarta-sans/400.css';
import '@fontsource/plus-jakarta-sans/600.css';
import '@fontsource/noto-sans-devanagari/400.css';
import { createRoot } from 'react-dom/client';
import './index.css';

// Placeholder only: screens arrive in F2+ after the red tests exist.
const container = document.getElementById('app');
if (container) {
  createRoot(container).render(<div data-ready="true" />);
}
