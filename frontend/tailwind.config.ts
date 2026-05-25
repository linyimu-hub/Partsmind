import type { Config } from "tailwindcss";
const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: { 50:"#EBF3FD", 500:"#378ADD", 600:"#185FA5", 700:"#0c4070" },
      },
    },
  },
  plugins: [],
};
export default config;
