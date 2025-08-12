/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './templates/*.html',        
    './static/**/*.js',
    './static/**/*.css',
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
