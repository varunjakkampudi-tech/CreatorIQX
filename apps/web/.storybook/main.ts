import type { StorybookConfig } from "@storybook/nextjs-vite";

/**
 * Storybook config for the design-system primitives (P0-083). The
 * accessibility gate is not the interactive addon-a11y panel here - it's a
 * separate Playwright + axe-core scan (tests/e2e/a11y.spec.ts) over the
 * static build's stories, which is the part CI actually fails on.
 * addon-a11y stays in for the same checks while browsing Storybook by hand.
 */
const config: StorybookConfig = {
  stories: ["../src/components/ui/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-a11y"],
  framework: {
    name: "@storybook/nextjs-vite",
    options: {},
  },
};

export default config;
