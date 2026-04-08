export function isAssetLocalhostUrl(value: string): boolean {
  if (!value) return false;
  const lower = value.toLowerCase();
  return (
    lower.startsWith("http://asset.localhost/") ||
    lower.startsWith("https://asset.localhost/") ||
    lower.startsWith("asset://localhost/")
  );
}

export function assertRawFilePathForBackend(path: string, context: string): void {
  if (!isAssetLocalhostUrl(path)) return;
  throw new Error(
    `[${context}] asset.localhost URL cannot be sent to the backend. Use the raw local file path instead.`,
  );
}

export function tryDecodeAssetLocalhostUrl(url: string): string | null {
  const match = url.match(/^https?:\/\/asset\.localhost\/(.+)$/i) ?? url.match(/^asset:\/\/localhost\/(.+)$/i);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}
