import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/providers/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        nunito: ['var(--font-nunito)', 'Hiragino Round Gothic Pro', 'sans-serif'],
      },
      colors: {
        quest: {
          violet: '#7C3AED',
          pink:   '#EC4899',
          cyan:   '#06B6D4',
          emerald:'#10B981',
          amber:  '#F59E0B',
          coral:  '#F97316',
          cream:  '#FEFCE8',
          soft:   '#F5F3FF',
        },
      },
    },
  },
  plugins: [],
}

export default config
