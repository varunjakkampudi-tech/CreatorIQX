import js from "@eslint/js";
import nextPlugin from "@next/eslint-plugin-next";
import tseslint from "typescript-eslint";

/**
 * Forbids a raw hex color literal (#fff, #4f46e5, ...) anywhere in a
 * .ts/.tsx source file. Design tokens live only in src/app/globals.css
 * (spec section 11); components must reach every color through a token
 * utility such as bg-surface or text-ink. This is the lint rule P0-080's
 * acceptance criterion names ("lint rule forbids raw hex in components").
 */
const noRawHexInComponents = {
  rules: {
    "no-restricted-syntax": [
      "error",
      {
        selector: "Literal[value=/^#([0-9a-fA-F]{3,8})$/]",
        message:
          "No raw hex colors in components. Add or reuse a design token in src/app/globals.css and use its Tailwind utility instead.",
      },
    ],
  },
};

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    plugins: { "@next/next": nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
    },
  },
  {
    files: ["src/**/*.ts", "src/**/*.tsx"],
    ...noRawHexInComponents,
  },
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
);
