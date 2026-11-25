# Uploads

<!-- COUPLED:safe-name: docs -->
A file is stored under the name it was uploaded with, in lowercase, with each run of characters
other than letters, digits, dots and hyphens replaced by one hyphen, and no hyphen at either end.
<!-- COUPLED:safe-name:END -->

<!-- COUPLED:storage-event: docs -->
Once a file is stored, the object store sends a notice naming its bucket, its key, its size in
bytes and its ETag, and the upload is marked stored.
<!-- COUPLED:storage-event:END -->
