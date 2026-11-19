"""File override: read the contents of S3-stored files from S3.

After upload, the controller deletes the local copy and rewrites file_url to
either the signed-download endpoint (private files) or
<endpoint>/<bucket>/<key> (public files), and stores the S3 key in
content_hash. Core File.get_content() only reads from local disk, so anything
that needs the bytes (email attachments, inline images, zip downloads)
failed with FileNotFoundError. This override fetches them from S3 instead.
"""

from urllib.parse import unquote

import frappe
from frappe.core.doctype.file.file import FILE_ENCODING_OPTIONS, File

GENERATE_FILE_URL = "/api/method/frappe_s3_attachment.controller.generate_file"


class S3File(File):
	def get_s3_key(self) -> str | None:
		"""Return the S3 key for this file, or None if it is not stored in S3."""
		file_url = self.file_url or ""
		if file_url.startswith(GENERATE_FILE_URL):
			if self.content_hash and "/" in self.content_hash:
				return self.content_hash
			# Fallback: parse ?key=...&file_name=... (the key is written unencoded)
			query = file_url.split("?", 1)[-1]
			if query.startswith("key="):
				return unquote(query[len("key=") :].split("&file_name=", 1)[0])
			return None
		# Public files: <endpoint>/<bucket>/<key>, key also kept in content_hash
		if (
			file_url.startswith("http")
			and self.content_hash
			and "/" in self.content_hash
			and file_url.endswith("/" + self.content_hash)
		):
			return self.content_hash
		return None

	def get_content(self, encodings=None) -> bytes | str:
		if self.is_folder or self.get("content"):
			return super().get_content(encodings)

		key = self.get_s3_key()
		if not key:
			return super().get_content(encodings)

		from frappe_s3_attachment.controller import S3Operations

		content = S3Operations().read_file_from_s3(key)["Body"].read()

		# Same decoding behaviour as core: text files come back as str, binary as bytes
		for encoding in encodings or FILE_ENCODING_OPTIONS:
			try:
				content = content.decode(encoding)
				break
			except UnicodeDecodeError:
				continue

		self._content = content
		return content
