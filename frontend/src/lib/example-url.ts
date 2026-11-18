/** Normaliza domínios informados sem protocolo para HTTPS. */
export function normalizeExampleUrl(value: string | null | undefined) {
  const trimmed = value?.trim();
  if (!trimmed || /[\\\s\u0000-\u001f\u007f]/.test(trimmed)) return null;

  const hasScheme = /^[a-z][a-z\d+.-]*:/i.test(trimmed);
  if (hasScheme && !/^https?:\/\//i.test(trimmed)) return null;
  const candidate = hasScheme ? trimmed : `https://${trimmed}`;
  try {
    const url = new URL(candidate);
    if (
      !/^https?:$/.test(url.protocol) ||
      !url.hostname ||
      url.username ||
      url.password
    )
      return null;
    return candidate.length <= 1000 ? candidate : null;
  } catch {
    return null;
  }
}
