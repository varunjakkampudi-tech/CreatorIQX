import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Input } from "./input";

describe("Input", () => {
  it("accepts typed text", async () => {
    render(<Input aria-label="Channel name" />);
    const input = screen.getByRole("textbox", { name: "Channel name" });

    await userEvent.type(input, "CreatorIQX");

    expect(input).toHaveValue("CreatorIQX");
  });

  it("exposes aria-invalid for a caller-driven error state", () => {
    render(<Input aria-label="Channel name" aria-invalid="true" />);
    expect(
      screen.getByRole("textbox", { name: "Channel name" }),
    ).toHaveAttribute("aria-invalid", "true");
  });
});
