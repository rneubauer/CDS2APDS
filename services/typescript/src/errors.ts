/** Service errors mapped to the response envelope (docs/03-link-service.md §3.2). */

export class ServiceError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
    this.name = "ServiceError";
  }
}

export const invalidRequest = (message: string) => new ServiceError(400, "invalid_request", message);
export const unauthorized = (message: string) => new ServiceError(401, "unauthorized", message);
export const notFound = (message: string) => new ServiceError(404, "not_found", message);
export const upstreamError = (message: string) => new ServiceError(502, "upstream_error", message);
