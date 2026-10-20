# Security and demo boundaries

Use fictitious records only. Readers share the demo workspace; the app does not isolate claims by patient or owner and is not a healthcare production baseline.

Report suspected vulnerabilities privately to the repository owner through GitHub. If private vulnerability reporting is enabled, use Security > Report a vulnerability. Otherwise contact the owner privately before opening an issue containing sensitive details. Do not include credentials or patient data.

The main branch is the supported version. Review dependency update pull requests and run CI before merging. Changes to database access, identity, or infrastructure also require deployment checks in the target environment.

Structured application events omit request bodies, tokens, queries, claim notes, and patient fields. Claim history remains in the database; it is not an immutable external audit store. Hosting administrators can access configured bootstrap credentials. Restrict their permissions and rotate both database credentials when needed.

The in-process API throttle is a small demo safeguard, not distributed abuse protection. Each instance maintains its own counters; users behind a shared proxy may share a limit. Review proxy trust and add an appropriate gateway policy before exposing a busy or broadly shared deployment.
