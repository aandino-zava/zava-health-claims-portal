# Security and demo boundaries

Use fictitious data only. Authorized readers share the workspace; claims are not isolated by patient or owner. This is a demo, not a production healthcare baseline.

Report suspected vulnerabilities privately to the repository owner. Use **Security → Report a vulnerability** if enabled; otherwise contact the owner privately. Keep credentials and patient information out of issues.

`main` is the supported branch. Review dependency updates and run CI before merging. Database, identity, and infrastructure changes also need checks in the target environment.

Application events omit bodies, queries, tokens, notes, and personal fields. Claim history stays in PostgreSQL and is not an immutable audit store. Hosting administrators can access bootstrap credentials in settings; restrict those permissions and rotate both database credentials when needed.

API throttling is per instance and client address. Users behind a proxy can share limits. Review proxy trust and add suitable gateway controls before expanding access. See [deployment boundaries](docs/DEPLOYMENT.md#operational-boundaries) and [validation](docs/VALIDATION.md).
