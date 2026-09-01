import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../src/client";
import { createTicketsApi } from "../src/tickets";

function mockFetchOnce(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("tickets api", () => {
  it("returns the raw PagedResponse (no extra unwrapping needed)", async () => {
    mockFetchOnce({ data: [], page: 1, page_size: 20, total: 0, total_pages: 0 });
    const tickets = createTicketsApi(new ApiClient({ baseUrl: "http://api.test" }));

    const result = await tickets.search("o1");

    expect(result).toEqual({ data: [], page: 1, page_size: 20, total: 0, total_pages: 0 });
  });

  it("builds a query string only from the params that were actually provided", async () => {
    const fetchMock = mockFetchOnce({ data: [], page: 2, page_size: 10, total: 0, total_pages: 0 });
    const tickets = createTicketsApi(new ApiClient({ baseUrl: "http://api.test" }));

    await tickets.search("o1", { page: 2, page_size: 10, status: "open", sort: "-created_at" });

    const [url] = fetchMock.mock.calls[0] as [string];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe("/api/v1/organizations/o1/tickets");
    expect(parsed.searchParams.get("page")).toBe("2");
    expect(parsed.searchParams.get("page_size")).toBe("10");
    expect(parsed.searchParams.get("status")).toBe("open");
    expect(parsed.searchParams.get("sort")).toBe("-created_at");
  });

  it("omits the query string entirely when no params are given", async () => {
    const fetchMock = mockFetchOnce({ data: [], page: 1, page_size: 20, total: 0, total_pages: 0 });
    const tickets = createTicketsApi(new ApiClient({ baseUrl: "http://api.test" }));

    await tickets.search("o1");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("http://api.test/api/v1/organizations/o1/tickets");
  });
});
