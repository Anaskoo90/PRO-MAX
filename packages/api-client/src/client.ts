import type { ErrorDetail, ErrorResponse } from "./types";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];

  constructor(status: number, body: ErrorResponse) {
    super(body.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

export type AccessTokenProvider = () => string | null;

export interface ApiClientOptions {
  baseUrl: string;
  getAccessToken?: AccessTokenProvider;
}

/** Thin fetch wrapper: attaches the bearer token, parses the standard
 * DataResponse/PagedResponse envelope, and turns a non-2xx ErrorResponse
 * into a typed ApiRequestError instead of a bare failed Response. */
export class ApiClient {
  private readonly baseUrl: string;
  private readonly getAccessToken?: AccessTokenProvider;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.getAccessToken = options.getAccessToken;
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    const token = this.getAccessToken?.();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });

    if (response.status === 204) {
      return undefined as T;
    }

    const body = (await response.json()) as unknown;

    if (!response.ok) {
      throw new ApiRequestError(response.status, body as ErrorResponse);
    }

    return body as T;
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "GET" });
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) });
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }
}
