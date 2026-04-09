/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './templates/*.html',        
    './static/**/*.js',
    './static/**/*.css',
    './**/*.py',
  ],
  safelist: [
    'bg-red-100',
    'text-red-800',
    'bg-green-100',
    'text-green-800',
    'bg-yellow-100',
    'text-yellow-800',
    'bg-blue-100',
    'text-blue-800',
    'bg-blue-50',
    'text-blue-700',
    'bg-gray-100',
    'text-gray-700',
    'bg-black/40',
    'bg-silhouette-overlay',
  ],
  theme: {
    extend: {
      fontFamily: {
        karla: ['Karla', 'sans-serif'],
      },
      padding: {
        '12': '3rem',   // 48px
        '14': '3.5rem', // 56px
        '16': '4rem',   // 64px
        '20': '5rem',   // 80px
        '24': '6rem',   // 96px
        '32': '8rem',   // 128px
      },
    },
  },
  plugins: [],
}
