import { ApiError } from "./index";

/** FastapiAdmin native response envelope, same HttpOnly login session. */
export async function systemApi(path: string, method = "GET", data?: unknown) {
  const response = await fetch(`/api/v1/system${path}`, {
    method, credentials: "same-origin",
    headers: data === undefined ? {} : { "Content-Type": "application/json" },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  });
  const body = await response.json();
  if (!response.ok || body.success === false) throw new ApiError(response.status, body.msg || "操作失败");
  return body.data;
}
