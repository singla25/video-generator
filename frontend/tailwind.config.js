/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        page: '#F6F7F9',
        card: '#FFFFFF',
        ink: '#1B2430',
        muted: '#6B7480',
        line: '#E4E7EC',
        emerald: { DEFAULT: '#1E7A5A' },
        lime: { DEFAULT: '#A6E07A' },
        mint: { DEFAULT: '#E6F6EE' },
        status: {
          completed: '#1E7A5A',
          processing: '#2F6FDE',
          queued: '#7A828E',
          failed: '#D43F3F',
          skipped: '#D98A0B',
        },
      },
      borderRadius: { card: '14px', tile: '12px' },
      borderWidth: { DEFAULT: '1px' },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', '"Noto Sans Devanagari"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
