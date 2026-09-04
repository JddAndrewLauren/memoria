import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunButton, type Step } from "./DirectRun";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("a direct run button", () => {
  it("remains operable when StrictMode rehearses an effect cleanup", async () => {
    const step = vi.fn<() => Promise<Step>>().mockResolvedValue({
      done: true,
      canContinue: false,
      summary: "one step recorded",
    });
    render(
      <StrictMode>
        <RunButton label="Run" runningLabel="Running…" step={step} />
      </StrictMode>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByText("one step recorded")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
    expect(step).toHaveBeenCalledTimes(1);
  });

  it("stops after the current metered step when it unmounts", async () => {
    const first = deferred<Step>();
    const step = vi
      .fn<() => Promise<Step>>()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValueOnce({
        done: true,
        canContinue: false,
        summary: "unexpected second call",
      });
    const view = render(
      <RunButton label="Run" runningLabel="Running…" step={step} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(step).toHaveBeenCalledTimes(1);
    view.unmount();

    await act(async () => {
      first.resolve({ done: false, canContinue: true, summary: "one step recorded" });
      await first.promise;
    });
    await waitFor(() => expect(step).toHaveBeenCalledTimes(1));
  });

  it("refreshes completed work when a later step fails", async () => {
    const onFinished = vi.fn();
    const step = vi
      .fn<() => Promise<Step>>()
      .mockResolvedValueOnce({ done: false, canContinue: true, summary: "one step recorded" })
      .mockRejectedValueOnce(new Error("later step failed"));
    render(
      <RunButton
        label="Run"
        runningLabel="Running…"
        step={step}
        onFinished={onFinished}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByText("The run failed.")).toBeInTheDocument();
    expect(step).toHaveBeenCalledTimes(2);
    expect(onFinished).toHaveBeenCalledTimes(1);
  });

  it("requires an explicit retry when a step makes no progress", async () => {
    const step = vi
      .fn<() => Promise<Step>>()
      .mockResolvedValueOnce({ done: false, canContinue: false, summary: "nothing recorded" })
      .mockResolvedValueOnce({
        done: true,
        canContinue: false,
        summary: "unexpected automatic retry",
      });
    render(<RunButton label="Run" runningLabel="Running…" step={step} />);

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByText("nothing recorded")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
    expect(step).toHaveBeenCalledTimes(1);
  });
});
