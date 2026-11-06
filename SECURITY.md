# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the URLs, URL-list files, and folders you name, and it writes one file: the sitemap you ask for with `-o` (or prints it with `--stdout`). It never changes an input file.

If you find a case where the tool changes an input file, writes a sitemap when the input has a problem, or writes a URL that was not in the input, please open an issue describing the exact commands and input. Do not include any real secret in the report.
