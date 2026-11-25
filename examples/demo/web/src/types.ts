// An upload, as the API returns it.

// COUPLED:upload-status: web
export type UploadStatus = "pending" | "stored" | "rejected";

// COUPLED:upload-shape: type
export interface Upload {
  id: string;
  name: string;
  sizeBytes: number;
  status: UploadStatus;
}
// COUPLED:upload-shape:END
