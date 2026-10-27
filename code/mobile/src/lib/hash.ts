// SHA-256 hashing utility for client-side duplicate document detection
export async function computeFileSha256(file: any): Promise<string | null> {
  try {
    if (typeof window !== 'undefined' && window.crypto?.subtle) {
      let buffer: ArrayBuffer | null = null;
      if (file instanceof Blob || (typeof File !== 'undefined' && file instanceof File)) {
        buffer = await file.arrayBuffer();
      } else if (file?.file instanceof Blob) {
        buffer = await file.file.arrayBuffer();
      }
      if (buffer) {
        const hashBuffer = await window.crypto.subtle.digest('SHA-256', buffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
      }
    }
  } catch (e) {
    // Fall back if subtle crypto is unavailable or file read fails
  }
  return null;
}
