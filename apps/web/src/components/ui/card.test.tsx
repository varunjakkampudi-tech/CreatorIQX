import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "./card";

describe("Card", () => {
  it("renders its children inside the surface container", () => {
    render(
      <Card>
        <p>Channel health score</p>
      </Card>,
    );
    expect(screen.getByText("Channel health score")).toBeInTheDocument();
  });
});
