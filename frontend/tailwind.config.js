/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        oxxo: {
          red:    '#CC2127',
          yellow: '#FFD200',
          dark:   '#1A1A1A',
          panel:  '#2C2C2C',
        },
      },
    },
  },
  plugins: [],
}
