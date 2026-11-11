export async function employeeRequest<T>(path: string, body?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/chatbot/employee' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(
      typeof data?.detail === 'string' ? data.detail : 'Không thể gửi yêu cầu. Vui lòng thử lại.',
      { cause: response.status },
    )
  }
  return data
}

export function sessionExpired(error: unknown) {
  return error instanceof Error && (error.cause === 401 || error.cause === 403)
}
