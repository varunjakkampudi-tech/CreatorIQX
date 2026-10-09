import js from "@eslint/js";
import nextPlugin from "@next/eslint-plugin-next";
import tseslint from "typescript-eslint";
import noRawJsxText from "./eslint-rules/no-raw-jsx-text.mjs";

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
      // typescript-eslint's "recommended" preset only warns on `any`
      // (spec section 12: "TypeScript: strict, no `any`" - a warning
      // doesn't fail `eslint .`, so P0-012 raises it to an error).
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  {
    files: ["src/**/*.ts", "src/**/*.tsx"],
    ...noRawHexInComponents,
  },
  {
    // Test fixtures (*.test.tsx) and Storybook stories (*.stories.tsx)
    // aren't product copy - a test's "Save" button label or a story's
    // demo text needs no translation key.
    files: ["src/**/*.tsx"],
    ignores: ["**/*.test.tsx", "**/*.stories.tsx"],
    plugins: { local: noRawJsxText },
    rules: { "local/no-raw-jsx-text": "error" },
  },
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "storybook-static/**",
    ],
  },
);
