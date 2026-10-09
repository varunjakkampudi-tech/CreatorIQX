import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Skeleton } from "./skeleton";

describe("Skeleton", () => {
  it("is hidden from assistive technology, since it has nothing to announce", () => {
    const { container } = render(<Skeleton className="h-4 w-32" />);
    const skeleton = container.firstElementChild;
    expect(skeleton).toHaveAttribute("aria-hidden", "true");
  });
});
