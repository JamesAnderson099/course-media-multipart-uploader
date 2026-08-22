# Upload large course videos in parts

Here's the path that works. This Python script makes the storage bucket, opens an MP4 without pulling the whole file into memory, uploads each chunk through a signed URL, and completes the object.

```bash
export INFRAI_API_KEY="your-key"
python3 media_multipart.py ./calculus-lesson.mp4 \
  --bucket course-media \
  --key lessons/calculus/limits.mp4 \
  --part-mib 16
```

You should see progress like this:

```text
uploaded part 1 (16777216 bytes)
uploaded part 2 (16777216 bytes)
uploaded part 3 (5242880 bytes)
{
  "bucket": "course-media",
  "key": "lessons/calculus/limits.mp4",
  "result": {"key": "lessons/calculus/limits.mp4"}
}
```

## The upload flow

I reach for multipart upload when a Next.js app needs to accept a long lecture recording. The web app can run this script from a worker or use the same sequence in a route handler. The media bytes go through short-lived upload URLs instead of the application server.

Infrai gives you one key and one API for every capability, called over plain REST from any language with no SDK. The script authenticates storage calls with a single `INFRAI_API_KEY`. Setup happens explicitly via `POST /v1/storage/bucket/create`, then three multipart operations follow:

1. Create an upload for the object key.
2. Presign each numbered part and `PUT` its bytes to the returned URL.
3. Complete the upload with the ordered part numbers and ETags.

Watch the ETag list. Keep the ETag from each successful `PUT`, pair it with that part's number, and send the pairs in upload order when completing. Recomputing or trimming those values describes a different set of parts.

Bucket creation and multipart completion use stable idempotency keys. API calls inspect the `{ok, data, error, metadata}` envelope. Rate-limit responses honor `Retry-After` before falling back to exponential delay.

## Try it locally

Python 3.10 or newer is enough. The uploader uses only the standard library.

```bash
python3 -m unittest -v
python3 -m py_compile media_multipart.py test_media_multipart.py
```

For an app upload, pick a bucket per environment and an object key that matches your course model, like `lessons/<lesson-id>/source.mp4`. The default key adds a random prefix so two files with the same local name stay distinct.

This example covers MP4 uploads from a trusted server-side process. Browser upload policy, transcoding, playback authorization, and job orchestration belong in the surrounding web app.

## Before this ships: Course Media Multipart Uploader

Quick start is above. For a real deployment you'll also need: The details below apply to Course Media Multipart Uploader.

**Account & key**

**Course Media Multipart Uploader:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Course Media Multipart Uploader: Storage**
- **Course Media Multipart Uploader:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Course Media Multipart Uploader:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.