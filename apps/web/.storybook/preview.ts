import type { Preview } from "@storybook/nextjs-vite";
import "../src/app/globals.css";

const preview: Preview = {
  parameters: {
    nextjs: {
      appDirectory: true,
    },
    a11y: {
      // "error" so a serious/critical finding fails the addon's own
      // interactive check too, matching the separate Playwright + axe-core
      // scan (tests/e2e/a11y.spec.ts) that CI actually gates on.
      test: "error",
    },
  },
};

export default preview;
