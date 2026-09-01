// Mirrors app.platform_core.api.responses / app.platform_core.errors.responses
// on the backend — the standard envelope every GuildDesk API response uses.

export interface ErrorDetail {
  field: string | null;
  message: string;
}

export interface ErrorResponse {
  code: string;
  message: string;
  correlation_id: string | null;
  details: ErrorDetail[];
}

export interface DataResponse<T> {
  data: T;
}

export interface PagedResponse<T> {
  data: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
