/**
 * dependency-cruiser config (P0-012). apps/web has no hexagonal layers
 * (that's the backend's architecture, enforced separately by
 * import-linter) - but it does have one boundary worth a tool, not just a
 * code-review habit: the shared design-system primitives in
 * src/components/ui must stay reusable outside this app's own routes, so
 * they may never import from src/app. The no-circular check also guards
 * against import cycles creeping into a frontend that will grow a lot of
 * modules (spec section 12: "Module boundaries enforced by tooling").
 *
 * @type {import('dependency-cruiser').IConfiguration}
 */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "Circular imports make modules hard to reason about and to test in isolation.",
      from: {},
      to: { circular: true },
    },
    {
      name: "ui-primitives-no-app-imports",
      severity: "error",
      comment:
        "src/components/ui holds the shared design-system primitives (Button, Input, Card, Skeleton, ...). They must stay app-agnostic so they're reusable by any screen, so they may not import from src/app.",
      from: { path: "^src/components/ui" },
      to: { path: "^src/app" },
    },
  ],
  options: {
    // Don't descend into node_modules - without this, resolving type-only
    // imports (tsPreCompilationDeps below) walks third-party .d.ts files
    // and reports *their* internal cycles as if they were this project's.
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "tsconfig.json" },
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default", "types"],
    },
    reporterOptions: {
      text: { highlightFocused: true },
    },
  },
};
